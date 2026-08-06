# Agent Skill 编写参考

本文用于编写调用 RunBuoy 的 Codex/Agent Skill。目标是让 Agent 安全地把用户已授权执行的本地命令纳入
RunBuoy 监控，而不扩大执行权限、不泄露内容、不暗示手机可以控制电脑。

仓库已有 Skill 位于 [`skills/runbuoy`](../../skills/runbuoy)。本参考比现有 Skill 更完整，可作为后续拆分
`SKILL.md` 和 `references/` 的事实来源。

## 推荐触发边界

RunBuoy 会实际启动命令并产生远端状态，Skill 宜采用**显式触发**：

- 用户明确说“用 RunBuoy / `$runbuoy` 监控这个命令”；
- 或用户明确要求把运行状态发送到已配对 iPhone。

不要因用户只说“运行测试”“跑构建”就自动加 RunBuoy。RunBuoy 不授予执行命令的权限；目标命令仍必须在
Agent 原本获得的用户授权和沙箱规则内。

## 永久安全规则

Skill 必须始终遵守：

1. 只通过公开 `runbuoy` CLI 使用产品。
2. 不自行创建/操作 tmux session，不读 pane 推断状态。
3. 不直连 APNs，不读取/打印 Keyring 或 credential fallback。
4. 不伪造 `RUNBUOY_EVENT_SOCKET` / `RUNBUOY_EVENT_TOKEN`。
5. 不建立 Server→Machine 轮询、控制队列、WebSocket、SSH、隧道或 terminal stream。
6. 不声称 iPhone 可以取消、重试、批准、输入、回复 Agent 或 attach。
7. 不把完整 argv、cwd、环境、源码、stdout/stderr、terminal frame 放进 title/message。
8. 除非用户明确要求共享日志末尾片段，否则不加 `--share-log-tail`。
9. 不根据时间、日志体积或主观阶段虚构百分比/ETA。
10. 不为加入进度而修改用户代码，除非用户同时授权代码改动。

## 前置检查

推荐执行：

```bash
runbuoy doctor --json
runbuoy capabilities --json
```

解析 `doctor`：

- `local_ready=false`：本地 Python/平台/tmux/存储不满足，不能创建可靠 Run。
- `local_ready=true, delivery.paired=false`：完整保留本地执行、日志、status、attach、cancel；不创建
  RemoteClient。
- `local_ready=true, delivery.paired=true, delivery.reachable=false`：继续本地运行；事件写 outbox，上传失败
  只影响 delivery。
- `delivery.ready=true`：当前配对和 Server 可达；仍不保证 iPhone 最终送达。

默认 doctor 退出码只依赖 `local_ready`。仅当用户把远端交付就绪作为独立硬条件时使用
`runbuoy doctor --require-delivery`。`doctor` 只读诊断，不触发 sync。

解析 `capabilities`：

- 必须确认 `schema_version` 是 Skill 支持的版本；
- 使用返回的 `progress_modes`，不要从帮助文本猜；
- 必须保持 `remote_control=false`、`inbound_tcp=false` 的语义。

如果 `command -v runbuoy` 失败，用户明确的 RunBuoy 请求允许执行
`uv tool install --python 3.12 runbuoy`，再验证 version/doctor/capabilities。Python 项目只有在用户明确要求
接入/修改代码时才添加 API：PEP 621/uv 项目使用名为 `runbuoy` 的 optional extra，requirements 项目使用
独立 `requirements-runbuoy.txt`。完整步骤见[安装指导](installation.md)。sudo、系统包管理器或 curl installer
仍需先取得确认。

## 配对处理

配对需要用户在 iPhone 端确认，Agent 不能代替。

交互终端可提示用户执行：

```bash
runbuoy device pair
```

非交互工作流可在用户明确要求开始配对时：

```bash
runbuoy device pair --no-wait --json
```

安全返回里有 pairing 信息和 `runbuoy://pair/...` QR value，但没有 exchange secret。用户在 App 中扫描/粘贴并
确认后，再执行：

```bash
runbuoy device pair --resume --json
```

不要读取凭证存储来判断 secret；使用 `runbuoy device status --json`。

当前托管 iOS 只支持 Global。不要建议普通用户配置 `--region cn`。自托管必须在配对前让 CLI 和自有 App 构建
指向同一 Server。

## 是否能接管已经运行的命令

不能。当前 CLI 没有“按 PID 接管”“导入已有 tmux session”或“追踪外部 Run”的命令。RunBuoy 必须从一开始
通过 `runbuoy run -- <argv>` 启动目标，才能拥有 PTY、进程组、日志、Socket 和事件序列。

若命令已在 RunBuoy 外运行，Skill 可以：

- 说明无法无损接管；
- 在用户授权重启时用 RunBuoy 重新启动；
- 或只用 `runbuoy notify` 发送一次用户提供的安全状态。

不要杀掉或重启已有任务，除非用户明确授权。

## 进度模式决策

```text
程序已经使用 runbuoy SDK / emit？
  └─ 是 → structured
  └─ 否
      stdout 是否有稳定 current/total？
        └─ 是 → regex
        └─ 否
            是否有固定总数，且每个完成单元恰好有可匹配记录？
              └─ 是 → lines
              └─ 否 → indeterminate
```

### Structured

仅当现有程序已经上报，或用户授权你增加 instrumentation：

```bash
runbuoy run --progress structured -- command
```

不要假设安装 CLI 后目标 Python 就能 `import runbuoy`：`uv tool` 使用隔离环境。只有目标项目已经启用
RunBuoy optional extra，或用户授权增加时，才能添加 Python import；否则优先使用现有 instrumentation 或
PATH 中的 `runbuoy emit`。`runbuoy` distribution 是唯一 SDK/CLI 实现。

生成的业务代码必须通过 reporter abstraction 上报。若 RunBuoy 包可以完全缺失，只捕获
`ModuleNotFoundError` 且确认 `error.name == "runbuoy"` 后使用同签名 `NoopReporter`；不得用宽泛
`ImportError` 吞掉 RunBuoy 内部依赖损坏。默认 `get_reporter(required=False)` 在无上下文/Socket 失败时返回
`False`，业务继续。有限、单调、真实的工作单元才用 progress；未知总量只用 phase/message；并发由单一
coordinator 汇总。

### Regex

必须确认捕获组 1=current、2=total 且都是数字：

```bash
runbuoy run \
  --progress regex \
  --pattern '^PROGRESS: ([0-9]+)/([0-9]+)$' \
  -- command
```

不要用会匹配普通日志数字的宽泛正则。

### Lines

必须有正 total 和真实的一记录一完成单元语义：

```bash
runbuoy run \
  --progress lines \
  --total 100 \
  --match '^DONE$' \
  -- command
```

### Indeterminate

无法证明 current/total 时使用：

```bash
runbuoy run --progress indeterminate -- command
```

这不是降级失败，而是诚实状态；iPhone 仍有状态、阶段、心跳和结果。

## 安全标题生成

推荐 title 是简短的“工具/任务类别”，不是命令摘要。例如：

| 原命令语义 | 安全标题 |
| --- | --- |
| 构建发布版本 | `Release build` |
| 数据集导入 | `Dataset import` |
| 优化实验 | `Optimization experiment` |
| 单元测试 | `Test suite` |

禁止放入：

- 文件系统绝对路径；
- 完整参数和 flag values；
- branch 中的客户/工单秘密；
- URL query；
- token、key、password；
- 用户 prompt 或输入原文。

CLI 自带脱敏和自动 basename title，但 Agent 仍应选择上下文足够、信息最少的标题。

## 启动模板

标准非交互模板：

```bash
runbuoy run \
  --json \
  --non-interactive \
  --title "Safe title" \
  --progress indeterminate \
  -- command arg1 arg2
```

要求：

- `--` 后保持用户原始 argv 和顺序；
- 不静默改参数、工作目录或环境；
- 若命令本身依赖 shell pipeline/redirection，只在原本执行语义就需要 shell 时使用用户认可的 shell wrapper，
  不为 RunBuoy 额外改写；
- 默认 `automatic` Live Activity；只有用户明确要立即验证/显示时用 `--live-activity immediate`；
- 用户明确不要 Live Activity 时用 `--live-activity disabled`，但说明失败/长成功的普通通知回退仍可能存在。

## 是否使用 `--wait`

### 不等待

适合用户只想启动长期任务并拿到 Run ID：

```bash
runbuoy run --json --non-interactive ... -- command
```

CLI 只有在 tmux、ready nonce、Socket ACK 和 `run.started` 可靠交接后才返回 0。响应必须满足
`ok=true && detached=true && worker_ready=true`；这不代表目标最终成功，也不代表远端送达。

### 等待

若当前 Agent 任务必须知道目标真实结果：

```bash
runbuoy run --json --non-interactive --wait ... -- command
```

解析 stdout JSON 的 `result`，同时保留 CLI 退出码即目标退出码。不要因为 RunBuoy 包装而吞掉失败。

可靠 detached 交接后 Agent 应立即退出，不轮询、不保持终端、不使用 `&`/nohup。只有用户明确要求最终结果
才使用 `--wait`。

## 启动后应返回给用户

至少返回：

- Run ID；
- 安全标题；
- 已选 progress mode；
- Live Activity policy（若非默认尤其说明）；
- 当前 `delivery.paired/reachable/ready`；
- 这些**电脑本地**命令：

```bash
runbuoy status RUN_ID
runbuoy logs RUN_ID
runbuoy attach RUN_ID
runbuoy cancel RUN_ID
```

明确说明这些命令必须在执行电脑上使用；iPhone 不能调用。

## 机器可读 follow-up

### 一次状态

```bash
runbuoy status RUN_ID --json
```

解析：

```json
{
  "schema_version": 1,
  "run": {
    "run_id": "...",
    "status": "RUNNING",
    "progress": null,
    "phase": null,
    "safe_message": "Run started",
    "exit_code": null,
    "started_at": "...Z",
    "updated_at": "...Z",
    "ended_at": null
  }
}
```

### 多次观察

`status --watch --json` 是多行 JSON 流，只在 `updated_at` 改变时发新行并在 terminal 结束。
Agent 若只需要一次快照，不要使用 watch。

### 列表

```bash
runbuoy list --json
runbuoy list --all --limit 20 --json
```

### Run 引用

Skill 应优先保存完整 Run ID。人类命令可用唯一前缀；`@latest` 适合交互便利，不适合并发自动化。
`@active` 在多个活动 Run 时会报 ambiguous。

## JSON 错误

公开命令带 `--json` 时，stderr 形如：

```json
{
  "ok": false,
  "error": {
    "code": "not_paired",
    "message": "this machine is not paired",
    "hint": "Run `runbuoy device pair` ..."
  }
}
```

Agent 应基于 `code` 分支，向用户转述 message/hint，不要把未知错误当作成功。常见 code：

```text
run_not_found
ambiguous_run
worker_handoff_failed
platform_unsupported
tmux_unavailable
local_storage_unavailable
local_event_unavailable
sync_busy
log_not_ready
session_not_active
worker_unreachable
cancel_rejected
not_paired
server_unreachable
notification_failed
pairing_failed
machine_name_sync_pending
```

`machine_name_sync_pending` 的本地保存已成功，但远端同步尚未完成；不要建议用户重复改成别的名字，
可等网络恢复后启动 Run 或重试同一配置。

## 日志和隐私

默认启动必须省略 `--share-log-tail`。只有用户明确表达“把末尾 N 行发到手机”且 N 为 1–100 时才加。

即使用户同意，也应提醒：

- 这是 remote upload；
- 自动脱敏不覆盖所有业务 secret；
- 完整日志仍只应通过本地 `runbuoy logs RUN_ID` 查看；
- Server 最多保留共享片段 24 小时。

`lines --match` 与 `regex --pattern` 接受的完整记录会成为脱敏后的 safe message，也可能远端可见；structured
phase/message/attention 同样可能远端可见。它们不是“仅本地解析”。

Agent 不应为了总结 Run 自动读取完整本地日志，除非用户也要求查看/分析日志。

## 通知 Skill 路径

用户只需要一次消息、不需要托管命令：

```bash
runbuoy notify \
  --json \
  --title "Release build" \
  --body "Build completed" \
  --level success
```

先用 `--dry-run --json` 可检查脱敏结果。title/body/fields 同样只能包含用户认可的安全内容。
Server accepted 不是 iPhone delivered；措辞应为“服务器已接受通知”。

## 本地取消

只有用户明确要求取消目标时：

```bash
runbuoy cancel RUN_ID --json
runbuoy status RUN_ID --json
```

取消是有破坏性的本地进程操作。先用完整 Run ID 解析目标；不要用 `@active` 取消并发中的不确定任务。
取消成功响应只表示请求 accepted，应再确认 terminal `CANCELLED`。

永远不要描述成“从手机取消”。

## 不应由 Skill 自动做的事

- `runbuoy history prune`：永久删除，应由用户明确要求、先 dry-run，再确认范围。
- `runbuoy config set --region/--server-url`：改变数据域且配对后锁定，必须由用户明确选择。
- `runbuoy config set --machine-name`：远端可见且可能暴露语义，需用户明确同意。
- `completion install`：修改 shell 配置，只有用户要求时执行。
- `attach`：接管当前交互终端，通常只返回命令给用户，不由 Agent 自动调用。
- 读取凭证文件、APNs token 或 manifest token。
- 创建 Webhook：当前没有 CLI 管理面，不能绕过 CLI 直接偷取 Machine credential。

## 推荐 Skill 文件结构

```text
skills/runbuoy/
├── SKILL.md                 # 触发边界、永久安全规则、主流程
└── references/
    ├── cli.md               # run/status/list/notify/错误和输出 schema
    ├── progress.md          # 四种 progress 决策与示例
    ├── privacy.md           # 标题、消息、日志片段边界
    ├── installation.md      # 全局 CLI 与项目 optional extra 路由
    ├── python-api.md        # Reporter、fallback 与业务隔离
    └── examples.md          # 常见命令模板
```

`SKILL.md` 保持短而强制，只链接 Agent 当前任务需要的 reference。功能事实可以从本文档集同步，
但不得把 iOS 的产品页面说明全部塞进执行 Skill。

## 建议的主流程伪代码

```text
if user did not explicitly request RunBuoy:
    do not trigger

run doctor --json
run capabilities --json
if local prerequisites fail:
    report exact failed checks and stop
if delivery not ready:
    explain pairing/server issue but continue local Run

classify progress using evidence from command/code/output contract
choose a short safe title
keep log sharing at 0 unless explicitly requested

run:
  runbuoy run --json --non-interactive --title ... --progress ... -- exact argv

parse JSON and exit status
require ok && detached && worker_ready for non-wait handoff
return run_id plus computer-local status/logs/attach commands
exit without polling after reliable detached handoff
never advertise phone controls
```

## Skill 验收清单

- [ ] 只有显式触发才启动 RunBuoy。
- [ ] preflight 同时检查 `doctor` 和 `capabilities`。
- [ ] title 不含路径、参数、用户输入或 secret。
- [ ] progress mode 有真实证据；否则 indeterminate。
- [ ] 原始 argv 在 `--` 后保持语义。
- [ ] 默认不共享日志 tail。
- [ ] JSON 输出和失败退出码被解析。
- [ ] 返回 Run ID 和本地 follow-up 命令。
- [ ] delivery 不可用没有阻止本地 Run；未出现虚假“推送成功”。
- [ ] detached 仅在 `ok && detached && worker_ready` 后结束 Agent turn，且未轮询。
- [ ] 清楚说明 iPhone 只读。
- [ ] 未直接操作 tmux、Socket、APNs、credential 或 raw Server control。
- [ ] 没有添加远程取消、批准、回复、输入、重试或 terminal 能力。
