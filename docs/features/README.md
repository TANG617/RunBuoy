# RunBuoy 功能总览（以当前代码为准）

本文档集是 RunBuoy 的“功能事实库”，供官网内容、使用文档和 Agent Skill 复用。
结论基于 2026-08-06 的当前工作树，而不是仅依据 README、PRD 或设计稿。凡是协议中已有字段、
但终端用户尚不能实际使用的能力，会明确标为“API/模型已存在，产品未落地”。

## 一句话定义

RunBuoy 把 Mac 或 Linux 上的命令、构建、实验和 Agent Run 的**安全状态投影**发送到
iPhone、锁定屏幕实时活动和灵动岛。执行仍完全发生在电脑上；手机只能接收和查看，不能控制。

```text
电脑上的命令
  → runbuoy CLI / 本地 Worker / 本地 SQLite
  → 出站 HTTPS
  → RunBuoy Server / PostgreSQL / APNs
  → iPhone App / 锁定屏幕 / 灵动岛
```

永久边界是 `Machine → Server → iPhone`。项目中没有远程终端、SSH、隧道、终端流、
服务器下发命令、手机取消/重试/批准、stdin、信号或控制 WebSocket。

代码依据：[`cli/src/runbuoy`](../../cli/src/runbuoy)、
[`server/app`](../../server/app)、[`apps/ios`](../../apps/ios)、
[`scripts/check_read_only_boundary.py`](../../scripts/check_read_only_boundary.py)。

## 组件和职责

| 组件 | 已实现职责 | 明确不负责 |
| --- | --- | --- |
| CLI | 配置和配对；创建 Run；本地列表、状态、日志、attach、取消；通知；演示；Shell 补全；历史清理 | 从手机接收操作、持续终端上传 |
| 本地 Worker | tmux 持久化、PTY、独立进程组、输出镜像、日志、进度解析、心跳、SQLite outbox、重试上传 | 依赖服务器决定命令生死 |
| Python SDK / `emit` | 通过带临时令牌的本地 Unix Socket 上报进度、阶段、消息和关注状态 | 直接访问服务器或 APNs |
| Server API | 设备引导、配对、鉴权、Run 投影、只读查询、通知、Webhook、接收偏好 | 机器控制队列或反向连接 |
| Push Worker | 事务 outbox、APNs Mock/Production、Live Activity 启动/更新/结束、重试和令牌失效 | 改变真实执行状态 |
| iOS App | 引导、扫码/粘贴配对、运行列表和详情、消息、电脑、接收偏好、本地缓存、功能体验 | 运行、取消、重试、attach 或回复 Agent |
| Widget | 锁定屏幕和灵动岛的只读实时活动、深链 | 按钮或操作控件 |
| Website | 中英双语产品介绍、安装/配对/运行/进度/安全/隐私/自托管文档、静态构建 | 提供 RunBuoy API、收集运行数据或充当控制台 |

## 面向用户的完整功能清单

### 1. 安装与环境诊断

- 支持 macOS、Linux、Python 3.12+。
- 持久 Run 依赖系统 `tmux`。
- 支持 `uv tool` 和 `pipx` 安装；CLI 当前版本来自
  [`cli/src/runbuoy/__init__.py`](../../cli/src/runbuoy/__init__.py)。
- `runbuoy doctor` 检查 Python、平台、tmux、配对、服务端 `/healthz` 和待发送事件。
- `runbuoy capabilities --json` 给脚本或 Agent 返回稳定的能力描述。
- Bash、Zsh、Fish、PowerShell、Pwsh 均可生成或安装补全；本地 Run ID 也参与补全。

完整安装、更新、项目 Python API 和配对步骤见[安装指导](../user-guide/installation.md)；命令细节见
[CLI 功能参考](cli.md)。

### 2. iPhone 配对与多电脑接收

- iOS 安装首次启动会创建 Device/Workspace 身份，并把设备凭证保存到 Keychain。
- 电脑执行 `runbuoy device pair`，终端显示 QR 和六位短码。
- QR 使用 `runbuoy://pair/...`，包含一次性 session/challenge、电脑显示名、平台和区域，
  不含长期机器凭证。
- 默认有效期 300 秒；同一配对只能 claim 一次、exchange 一次。
- 可用 `--no-wait` 保存待配对会话，扫码后用 `--resume` 完成交换。
- 一台 iPhone 可以订阅多台电脑。电脑名只能从 CLI 修改；iOS 只读。

### 3. 持久执行 Run

最小用法：

```bash
runbuoy run -- python3 experiment.py
```

实现行为：

- CLI 生成 UUIDv7 Run ID 和安全标题。
- 完整 argv、cwd、Socket 令牌仅写入权限为 `0600` 的本地 manifest。
- Run 和事件先写入本地 SQLite，再由独立 Worker 上传。
- Worker 在 tmux 中运行，通过 PTY 合并捕获 stdout/stderr，同时镜像到本地终端和日志。
- 目标进程位于独立进程组；网络失败不终止目标命令。
- 默认立即返回；`--wait` 等待结果，并把目标退出码作为 CLI 退出码。
- 真实状态包括 `CREATED`、`STARTING`、`RUNNING`、`SUCCEEDED`、`FAILED`、
  `CANCELLED`、`LOST`。

### 4. 四种诚实进度

- `indeterminate`：默认；没有真实分母时只显示运行中、阶段和已确认时间。
- `structured`：程序调用 Python SDK 或 `runbuoy emit`。
- `lines`：每条匹配输出代表一个有界工作单元。
- `regex`：输出中已有稳定的 current/total 两个数字捕获组。

RunBuoy 不根据已用时间猜百分比或 ETA。进度会限制在 `0...total`；正则进度会忽略倒退和
重复值。ETA 只有外部集成明确传入 `estimated_end_at` 时才可能显示，CLI/SDK 不自行生成。

详见 [进度与 SDK](progress-sdk.md)。

### 5. 本地查看和本地控制

```bash
runbuoy list
runbuoy status RUN_ID
runbuoy logs RUN_ID
runbuoy attach RUN_ID
runbuoy cancel RUN_ID
```

- `list/status/logs/attach/cancel` 只访问本地数据库、文件、tmux 或受保护的 Unix Socket。
- `status --watch` 在交互终端显示实时 Panel/进度条；活动 Run 60 秒无本地更新显示 Stale，
  `LOST` 显示 Offline。
- `logs -f` 跟随完整本地日志；执行该命令不会上传日志。
- `attach` 连接本地 tmux session。
- `cancel` 仅由本地 Worker 执行，按 SIGINT → SIGTERM → SIGKILL 升级，每级默认等待 3 秒。
- 完成记录可用 `history prune` 永久清理；默认保护尚未同步的事件。

这些能力不能从 iPhone 或 Server 触发。

### 6. 安全通知

```bash
runbuoy notify \
  --title "Build completed" \
  --body "Release build succeeded" \
  --level success \
  --field Target=iOS
```

- 不创建托管 Run。
- 级别为 `info`、`success`、`warning`、`error`。
- 支持 subtitle 和可重复的 `label=value` 字段。
- `--dry-run` 可在未配对时预览脱敏后的载荷。
- Server API 还接受 HTTPS `safe_link` 和 `expires_at`，但当前 CLI 没有对应选项，iOS 也不展示
  `safe_link`，因此不能作为当前面向用户的链接功能宣传。

### 7. 可选安全日志末尾片段

```bash
runbuoy run --share-log-tail 20 -- command
```

- 默认值为 0，必须显式选择 1–100 行。
- 上传前去 ANSI、做凭证模式脱敏、单行最多 500 字符、总 UTF-8 载荷最多约 16 KB。
- iOS 以“已上传的安全日志片段”单独标注；完整日志仍留在电脑上。
- Server 默认在 Run 结束 24 小时后清空片段。
- 脱敏只是纵深防御，不等于可以分享敏感输出。

### 8. iOS 运行查看

- 三个主 Tab：正在运行、历史、设置。
- 前台每 3 秒自动刷新，同时支持下拉和按钮刷新；通知到达或 App 回到前台也会刷新。
- 离线时读取带文件保护的本地快照，并显示缓存/离线横幅。
- 正在运行列表显示电脑、执行状态、阶段、百分比或不确定进度、电脑确认的执行时长和最近心跳。
- 历史页同时显示完成 Run 和通知消息，可按电脑过滤；每个区默认展示 5 条，可展开全部已加载数据。
- 详情页显示状态、健康、关注状态、进度、阶段、时间、显式 ETA、退出码、安全消息、按序事件 Feed、
  可选安全日志片段和 Run ID。
- 详情页可以复制 Run ID、复制安全消息和分享只包含标题/电脑/状态/安全消息的摘要。
- 电脑页显示平台、架构、CLI 版本、最近在线和配对时间；电脑图标是 iPhone 本地外观偏好。

详见 [iOS App 与 Live Activity](ios.md)。

### 9. Live Activity、锁定屏幕与灵动岛

- `automatic`：Run 开始后延迟 5 秒启动；5 秒内结束的短 Run 不启动。
- `immediate`：服务端收到开始状态后即可启动。
- `disabled`：不启动 Live Activity，但失败/长成功的普通通知回退仍可能发生。
- 每台 Device 最多保有 2 个 active/stale Live Activity；达到上限时新的 start 被抑制，
  当前实现不会自动替换旧 Activity。
- 有频繁更新权限时，普通进度最快约 1 秒一次；关闭后为至少 15 秒。
- 小于 1% 的进度变化会延后合并；阶段、关注、终态和失败为高优先级。
- Worker 每 15 秒发送一次心跳；活动载荷在最后一次电脑确认后 60 秒进入 stale。
- 显示的运行时长以 `createdAt → updatedAt` 计算，是静态的电脑确认值，不是手机自行递增的“看似在线”计时器。
- 结束后先显示“刚刚”，随后只显示完整分钟数；时间锚点为 `endedAt`，旧载荷回退到最终 `updatedAt`。
- 点击普通 Activity 打开 `runbuoy://runs/<uuid>`；本机功能体验 Activity 打开 `runbuoy://demo/...`。
- 无任何操作按钮。

### 10. 本机功能体验

iOS 设置中的“功能体验”不需要 CLI、配对或 Server：

- 在本机创建真实 ActivityKit Live Activity。
- 手动依次体验 Starting、不确定进度、72% 进度、Warning、Stale、Succeeded 或 Failed。
- 可安排 5 秒后的本地通知。
- Demo Activity 明确排除在服务端令牌同步之外，不会创建真实 Run 或上传数据。

CLI 也提供两种真实链路演示：

- `runbuoy demo notification`：发送固定安全通知。
- `runbuoy demo live-activity`：创建真实结构化 Run，可选择成功/失败、关注状态、8–300 秒时长。

### 11. Webhook 与外部 Run

Server 实现了 API 级 Webhook：

- 创建/撤销一个带独立 Bearer secret 的 Hook。
- Hook 发送通知。
- 用 external Run ID 幂等映射到确定 UUID，并追加 Run 事件。
- secret 只放 `Authorization: Bearer ...`，不放 URL。

当前 CLI 没有创建/列出/撤销 Webhook 的用户命令，因此它属于**集成 API 能力**，不是普通 CLI 工作流。
详见 [Server、推送与 Webhook](server.md)。

### 12. 自托管

- Docker Compose 运行 PostgreSQL、Alembic migration、FastAPI 和独立 outbox worker。
- Mock APNs 无需 Apple 凭证，发送尝试写入 `push_attempts`，用于开发和 CI。
- Production APNs 使用 HTTP/2、TLS、ES256 Provider Token 和加密保存的设备/Activity Token。
- 生产 Compose 只把 API 暴露在 `127.0.0.1:8000`，由 Caddy 提供 HTTPS。
- 需共同备份 PostgreSQL 与 Token 加密密钥。
- CLI 必须在配对前设置自托管 URL；iOS 当前没有服务器地址编辑 UI，自托管需用自有构建设置
  `RUNBUOY_API_BASE_URL`（或兼容性 UserDefaults 注入）指向同一服务。

## 数据边界

默认可远端出现：

- 安全标题、电脑 ID/显示名、来源；
- 执行/健康/关注状态；
- 真实进度、单位、阶段、安全消息；
- 事件顺序和时间、退出码、终止原因；
- 显式选择的安全日志末尾片段；
- App/CLI/OS/平台版本等配对元数据；
- APNs Token（服务端加密保存，不返回给 Machine）。

默认不会上传：

- 完整 argv 和命令参数；
- cwd、环境变量；
- 源码、文件内容、stdin；
- 完整 stdout/stderr、终端画面和按键；
- API Key、SSH Key、云凭证；
- tmux 内容或远程控制指令。

安全标题和用户显式填写的消息仍可能泄露项目语义，调用方必须主动选择安全文字。

## 当前代码事实与产品文案注意事项

以下内容尤其容易被旧文档或协议字段误导：

1. **当前 App 需要 iOS 18 或更高版本。** App、Widget、unit-test 和 UI-test target 均以 iOS 18.0
   为最低版本；iOS 26+ 使用 guarded Liquid Glass，iOS 18–25 使用完整的标准 SwiftUI fallback。
2. **托管 iOS 只启用 Global。** CLI 仍有 `--region cn` 和中国区 URL 常量，但 iOS 的
   `hostedRegions` 只有 Global，并把 China 兼容值归一到 Global；中国大陆独立托管尚不能作为可用功能宣传。
3. **自托管 App 没有服务器地址输入界面。** 需要自有构建或预置配置。
4. **Rich Message 当前按纯文本展示。** `fields` 会展示；Server 保存 `safe_link`，iOS 模型未消费它；
   没有已实现的 Markdown/HTML/WebView 渲染。
5. **`notification_policy` 只被保存，未参与推送决策。** CLI 也没有该选项，不应描述为已生效策略。
6. **iOS 的通知开关同时写 success/failure 两类接收偏好。** 它不撤销系统通知权限。
7. **“显示安全消息”主要是本地显示偏好。** 它隐藏详情中的安全消息区和历史消息区，但当前 Run Feed
   事件消息及分享摘要仍可能包含 safe message，不能描述成全局内容屏蔽。
8. **“停止接收”和“移除配对”当前都通过删除这台 Device 的 Machine subscription 实现。**
   `removeLocalPairing` 并未删除 Keychain Device 身份，也不会联系或控制 Machine。
9. **清除本地缓存不解除配对、不删服务端数据。** 前台后续刷新会重新下载仍有权限的数据。
10. **服务器不会定时改写 Run 的 `health_status`。** CLI 的本地 `status` 会在 60 秒后自行显示 Stale；
    Live Activity 使用 ActivityKit stale date；iOS App 列表则展示服务端投影中的 health 值。
11. **Live Activity 两条上限是容量抑制，不是动态抢占排序。** 满额后新 start 被 suppressed。
12. **Webhooks、`safe_link` 和任意外部 progress 字段属于 API 集成面。** 不要假设普通 CLI 用户已有对应管理 UI。
13. **CLI 的隔离安装不会给目标 Python 安装 import 库。** Python 接入应把唯一的 `runbuoy`
    distribution 放入名为 `runbuoy` 的 optional extra，默认业务环境可以不安装；无项目依赖时可使用
    `runbuoy emit`。

## 官网内容建议分层

官网首页适合只承诺：

- 电脑上的长任务，安全地出现在 iPhone；
- 真实进度、阶段、结果和需要关注状态；
- 锁定屏幕、灵动岛、通知和离线历史；
- 默认不上传命令参数、环境、源码或完整日志；
- 单向只读，手机不能控制电脑。

使用文档再展开：安装、配对、四种进度、本地命令、日志片段、通知、演示和自托管。
Webhook/API、APNs 和协议细节放在集成/运维文档中。Agent 的执行规则见
[Agent Skill 编写参考](../user-guide/agent-skill.md)。官网已有内容的维护和发布方法见
[官网内容、双语维护、构建与发布](../developer-guide/website-maintenance.md)。
