# CLI 功能参考

本文逐项覆盖当前 `runbuoy` CLI 的公开命令、参数、输出语义和本地副作用。命令定义以
[`cli/src/runbuoy/cli/app.py`](../../cli/src/runbuoy/cli/app.py) 为准。

## 安装要求

- macOS 或 Linux；不支持 Windows。
- Python 3.12+。
- `tmux`；没有它仍可查看帮助/配置，但不能创建持久 Run。

```bash
# macOS
brew install tmux
uv tool install runbuoy

# Debian / Ubuntu
sudo apt install tmux
pipx install runbuoy
```

升级使用原安装器：`uv tool upgrade runbuoy` 或 `pipx upgrade runbuoy`。

## 全局选项

| 用法 | 作用 |
| --- | --- |
| `runbuoy --version` | 输出 `runbuoy <version>` 并退出 |
| `runbuoy --no-color ...` | 关闭 Rich 终端样式 |
| `NO_COLOR=1 runbuoy ...` | 同样关闭颜色 |
| `runbuoy --help` | 显示按 Run 管理、诊断、自动化分组的帮助 |

## `runbuoy run`

```bash
runbuoy run [OPTIONS] -- <command> [args...]
```

### 基本行为

1. 校验参数并生成安全标题。
2. 创建本地 manifest、Run 目录和 SQLite 事件。
3. 启动名为 `runbuoy-<Run ID 前缀>` 的 detached tmux session。
4. Worker 初始化数据库、权限 0600 的 Socket 和 ready nonce；CLI 验证 tmux/nonce/Socket 并 ACK。
5. Worker 收到 ACK 后才用 argv 数组直接启动目标，不经过 shell 字符串拼接，并写入 `run.started`。
6. CLI 收到 `run.started`（或明确启动失败）后才返回。
7. 目标的 stdout/stderr 进入同一个 PTY，既写本地 `run.log`，也镜像到 tmux pane。
8. 本地事件先提交后上传；重复上传由 Server 幂等处理。
9. 默认打印 Run ID 和本地 follow-up 命令后返回，目标由 Worker/tmux 持续托管。

完整 argv、cwd、Socket 令牌和本地路径只在 manifest 中；远端先接收安全标题、来源和结构化事件。
配对和 Server 可达性从不作为本地启动条件：未配对时不创建 RemoteClient；已配对但不可达时事件保留在
本地 outbox，上传失败不改变目标退出码或本地控制能力。

### 全部公开选项

| 选项 | 默认 | 规则和效果 |
| --- | --- | --- |
| `--title TEXT` | 自动生成 | 最长 120 字符；单行；去 ANSI 和常见凭证。省略时通常只取可执行文件名，解释器可附脚本 basename |
| `--progress MODE` | `indeterminate` | `structured`、`lines`、`regex`、`indeterminate` |
| `--pattern REGEX` | 无 | `regex` 必填；至少两个捕获组，组 1=current、组 2=total |
| `--total NUMBER` | 无 | `lines` 必填且必须 > 0 |
| `--match REGEX` | 无 | `lines` 仅统计匹配记录；省略则所有非空终端记录都计数 |
| `--unit TEXT` | 无 | 进度单位，协议模型最多 40 字符 |
| `--share-log-tail N` | `0` | 0–100；终态时附带脱敏后的末尾 N 行 |
| `--live-activity POLICY` | `automatic` | `automatic`、`immediate`、`disabled` |
| `--json` | 关 | stdout 使用稳定 JSON；错误 JSON 输出到 stderr |
| `--non-interactive` | 关 | 关闭等待提示和终端专用反馈；不会改变目标命令 |
| `--wait` | 关 | 等待本地 `result.json`，并以目标退出码退出 |
| `--quiet`, `-q` | 关 | 隐藏人类可读的启动/完成输出；JSON 不受此项替代 |
| `--dry-run` | 关 | 只校验并区分远端字段和本地字段，不创建目录、数据库或 Run |

代码还有一个隐藏的 `--source`，供内置 demo 标记来源；不属于用户接口。`_worker` 也是内部命令，
用户和 Agent 不应直接调用。

### 标题生成

未传 `--title` 时：

- 普通命令只使用可执行文件 basename，例如 `/usr/bin/make release` → `make`。
- `python/python3/ruby/node/deno/bun/bash/sh/zsh SCRIPT` → `解释器 · 脚本 basename`。
- `cargo SUBCOMMAND`、`docker SUBCOMMAND` 会附带子命令。
- 参数、目录部分、控制字符和常见凭证模式不进入标题。

显式标题依然会做去 ANSI、凭证脱敏、换行合并和长度限制。它不能判断所有业务敏感词，
因此标题仍需由用户/Agent 主动保持抽象。

### `--dry-run` 输出

```bash
runbuoy run --dry-run --json --title "Safe title" -- command --secret local-only
```

返回的 `remote` 包含 title、source、progress mode、共享日志行数；`local_only` 包含完整 argv 和 cwd。
此模式不要求配对或 tmux。

### 启动 JSON

不带 `--wait` 时的大致结构：

```json
{
  "ok": true,
  "run_id": "019...",
  "title": "python3 · experiment.py",
  "status": "RUNNING",
  "detached": true,
  "worker_ready": true,
  "delivery": {
    "paired": true,
    "reachable": false,
    "ready": false
  },
  "live_activity_policy": "automatic",
  "local": {
    "status": "runbuoy status <full-id>",
    "logs": "runbuoy logs <full-id>",
    "attach": "runbuoy attach <full-id>",
    "cancel": "runbuoy cancel <full-id>"
  }
}
```

带 `--wait --json` 时会在同一对象增加 `result`；`ok` 取决于退出码是否为 0。目标失败时 JSON 仍会输出，
随后 CLI 以目标退出码退出。

### 退出和取消语义

- 未等待的成功启动：只有完成 ready/nonce/ACK/`run.started` 交接才退出 0，目标继续。
- `--wait`：返回目标真实退出码。
- 本地取消后，若目标由信号结束，公开退出码规范化为 130；状态为 `CANCELLED`。
- ACK 后 Worker/目标启动异常：写 `FAILED`、退出码 127、`worker_error`。
- ACK 前 CLI/Worker 失败或超时：Run 记录为 `LOST`，目标不得启动，CLI 返回 `worker_handoff_failed`。

## `runbuoy list`

```bash
runbuoy list [--all] [--status STATUS] [--limit N] [--watch] [--interval SEC] [--json]
```

- 默认只列活动 Run；`-a/--all` 包括终态历史。
- `--status` 接受 created、starting、running、succeeded、failed、cancelled、lost（大小写均可）。
  指定 status 后会在全部本地记录中筛选，不需要再加 `--all`。
- `--limit/-n` 为 1–200，默认 20。
- `--watch/-w` 持续刷新；`--interval` 为 0.2–60 秒，默认 1 秒。
- 人类输出列为 ID 前 12 位、标题、状态、百分比、开始时间和耗时。
- `--json` 返回 `{"schema_version":1,"runs":[...]}`；watch 模式会持续输出 JSON 行。
- 不构造 RemoteClient，不访问网络。

## `runbuoy status`

```bash
runbuoy status RUN_ID [--watch] [--interval SEC] [--json]
```

RUN_ID 可以是完整 ID、唯一前缀、`@latest` 或 `@active`。`@active` 只有在恰好一个活动 Run 时明确；
多个活动 Run 会要求选择 ID。

显示内容：Run ID、标题、执行状态、健康、进度、阶段、最新安全消息、开始/更新时间、耗时和退出码。

本地健康判定：

- `LOST` → Offline；
- 任一终态 → Healthy / final update confirmed；
- 活动 Run 距 `updated_at` 小于 60 秒 → Healthy；
- 达到 60 秒 → Stale。

交互终端使用 Panel 和确定/不确定进度条；`--watch` 原位刷新直到终态。非 TTY 输出表格；
`--watch --json` 只在 `updated_at` 变化时输出一个新 JSON 对象，适合作为 JSONL 消费。

JSON 的公开 Run 字段是：`run_id`、`title`、`source`、`status`、`progress`、`phase`、
`safe_message`、`exit_code`、`started_at`、`updated_at`、`ended_at`。时间统一输出 UTC 秒精度。

## `runbuoy logs`

```bash
runbuoy logs RUN_ID [--lines N] [--follow]
```

- 只读本地完整日志；不会因为查看而上传。
- `--lines/-n` 为 1–10000，默认最后 200 行。
- `--follow/-f` 先打印已有末尾，再调用本地 `tail -f` 跟随新增内容。
- 接受完整 ID、唯一前缀和 `@latest`。
- 日志尚未创建时返回 `log_not_ready`。

日志是 PTY 原始字节流，stdout/stderr 已合并，可能包含终端控制字符；它与可选上传的脱敏 tail 不同。

## `runbuoy attach`

```bash
runbuoy attach RUN_ID
```

- 只接受活动 Run 的完整 ID、唯一前缀或 `@active`。
- 执行 `tmux attach-session -t <recorded-session>`。
- tmux session 已消失时返回 `session_not_active`，不会根据 pane 内容猜状态。

## `runbuoy cancel`

```bash
runbuoy cancel RUN_ID [--json]
```

- 只接受活动 Run。
- 读取本地 manifest 中的 Socket 路径和临时令牌，通过权限 `0600` 的 Unix Socket 请求 Worker。
- Worker 对目标进程组依次发送 SIGINT、SIGTERM、SIGKILL，每级等待配置的 grace（默认 3 秒）。
- 成功只表示“本地取消请求已接受”，终态应再用 `status` 确认。
- JSON 成功值含 `requested: "local_cancel"`。

## `runbuoy notify`

```bash
runbuoy notify \
  --title TEXT \
  --body TEXT \
  [--subtitle TEXT] \
  [--level info|success|warning|error] \
  [--field label=value ...] \
  [--dry-run] [--json]
```

- title/body 必填；默认 level 为 info。
- `--field` 可重复，按第一个 `=` 分隔；label 不能为空。
- 本地限制：title 120、subtitle 120、body 2000、field label 80、value 300 字符，并进行脱敏。
- Server 模型最多接受 20 个 field；CLI 未预先限制个数，超出会由 Server 拒绝。
- `--dry-run` 输出脱敏后的 payload，不检查配对，不发送。
- 真发送要求机器凭证；Server 接受后不等于 APNs 已送达。
- CLI 当前不暴露 API 的 `safe_link`、`expires_at`、`run_id` 选项。

## `runbuoy device pair`

```bash
runbuoy device pair [--no-wait | --resume] [--timeout SEC] [--json]
```

- 首次使用会生成并持久化稳定的 `machine_<uuid7 hex>`。
- 默认创建会话、先显示 QR/六位码，再每 2 秒轮询，最多等 300 秒。
- `--timeout` 允许 5–600 秒；Server 默认会话本身只活 300 秒，调大不会延长服务端 TTL。
- `--no-wait` 保存 session ID 和 exchange secret 后立即返回。
- `--resume` 恢复保存的会话；两者不能并用。
- iPhone claim 后，CLI 用一次性 exchange secret 换取 Machine Bearer credential。
- JSON/JSONL 输出会过滤字段名含 secret、credential、token 的值；exchange secret 从不打印。

凭证优先保存在系统 Keyring；不可用或设置 `RUNBUOY_DISABLE_KEYRING=1` 时使用 mode `0600` 文件。

## `runbuoy device status`

```bash
runbuoy device status [--check-server] [--json]
```

显示 machine ID/name、是否已有 machine credential、是否有待完成配对、server URL。
`--check-server` 额外对 `/healthz` 做 2 秒有界请求。

## `runbuoy doctor`

```bash
runbuoy doctor [--require-delivery] [--verbose] [--json]
```

schema v2 明确拆分：

```json
{
  "schema_version": 2,
  "local_ready": true,
  "delivery": {"paired": true, "reachable": false, "ready": false},
  "pending_events": 12
}
```

- `local_ready`：本地 Python/平台/tmux/存储可用；默认退出码只依赖它。
- `delivery`：独立的配对、Server 可达和综合就绪状态，不降低本地能力。
- `pending_events`：全部未交付事件，包括处于 retry backoff 的事件。
- `--require-delivery` 在 `delivery.ready=false` 时非 0。
- `--verbose/-v` 增加 config/data/state/cache 路径。

`doctor` 只诊断，不触发 outbox 上传。

## `runbuoy sync`

```bash
runbuoy sync --json
```

显式重试所有 Run 的 pending events。机器必须已配对；未配对返回 `not_paired`。Worker 启动时也会尝试
恢复旧事件。所有 Worker 和手动 sync 通过本机全局文件租约保证同一时刻只有一个 outbox drainer；进程退出
会自动释放租约。失败事件保留并继续 backoff，Server 以 event ID 幂等处理重复请求。

## `runbuoy capabilities`

```bash
runbuoy capabilities --json
```

schema version 2 包含：CLI 版本、macOS/Linux、四种 progress mode、本地命令、Python API、detached
handoff、demo 命令、Shell 补全类型，以及以下边界布尔值：

```json
{
  "remote_control": false,
  "inbound_tcp": false,
  "full_logs_uploaded_by_default": false
}
```

这是 Agent/脚本发现能力的首选入口；不应通过解析 `--help` 猜能力。

## `runbuoy config`

```bash
runbuoy config
runbuoy config show [--json]
runbuoy config set [--region global|cn] [--server-url URL] [--machine-name TEXT] [--json]
runbuoy config path [--json]
```

### 配置规则

- 默认 region `global`，Server `https://api.runbuoy.cloud`。
- CLI 代码也映射 `cn` → `https://api-cn.runbuoy.cloud`，但当前官方 iOS App 只启用 Global；
  不应在正常托管流程中选择 `cn`。
- `--region` 和 `--server-url` 不能同次使用。
- 已配对后不能切换 region 或 server URL；这是数据域和凭证边界。
- `--server-url` 适合配对前选择自托管服务。
- machine name 最长 120 字符且脱敏；配对后立即 PATCH 到 Server。
- 若改名时离线，配置会先保存，本地 outbox 只保留最新名称，并返回
  `machine_name_sync_pending`（退出 1）；后续 Run uploader 会再尝试。
- iOS 没有改名界面。

`config show` 不输出 secret；会说明凭证存储为 `keyring-or-mode-0600-fallback`。
`config path` 返回配置、SQLite、数据、状态和缓存的解析路径。

## `runbuoy history prune`

```bash
runbuoy history prune \
  [--older-than 30d] [--limit 1000] \
  [--dry-run] [--yes] [--include-unsynced] [--json]
```

- duration 必须是正整数加 `m/h/d/w`，例如 `90m`、`24h`、`30d`、`8w`。
- 只匹配终态 Run；limit 1–10000。
- 默认排除含未送达事件的 Run。
- `--include-unsynced` 明确允许丢弃未送达事件。
- `--dry-run` 只列出候选。
- 真删除默认交互确认；`--yes/-y` 跳过确认。
- 仅删除 manifest 所在目录确实位于 RunBuoy state/runs 根下的路径。
- 删除本地 Run 文件、事件和数据库行，不可恢复；JSON 明确返回 `recoverable:false`。

## `runbuoy demo`

### 固定通知

```bash
runbuoy demo notification [--dry-run] [--json]
```

发送内置 success 通知，用于验证真实 Server/APNs 路径。dry-run 可在不发送时预览。

### 真实 Live Activity Run

```bash
runbuoy demo live-activity \
  [--duration 15] [--result success|failure] [--attention] [--wait] [--json]
```

- 先强制检查配对和 `/healthz`。
- duration 为 8–300 秒。
- 创建一个 `source=demo`、`structured`、`live-activity=immediate` 的真实托管 Run。
- 依次发送 5%、30%、65%、100% 及 Preparing/Downloading/Processing/Finishing。
- `--attention` 在 65% 时发送 ACTION_REQUIRED。
- `--result failure` 最终退出 1。
- `--wait` 才等待 demo 完成；否则像普通 Run 一样立即返回。

## `runbuoy emit`

```bash
runbuoy emit progress --current N --total N [--unit TEXT] [--phase TEXT] [--message TEXT]
runbuoy emit phase TEXT
runbuoy emit message TEXT
runbuoy emit attention TEXT [--status INFORMATION|WARNING|ACTION_REQUIRED]
```

这些命令必须在 RunBuoy 启动的目标进程树中调用，依赖注入的
`RUNBUOY_EVENT_SOCKET` 和 `RUNBUOY_EVENT_TOKEN`。它们只连接本地 Unix Socket。
详细规则见 [进度与 SDK](progress-sdk.md)。

## `runbuoy completion`

```bash
runbuoy completion show bash|zsh|fish|powershell|pwsh
runbuoy completion install bash|zsh|fish|powershell|pwsh
```

- `show` 只把确定的脚本打印到 stdout。
- `install` 由 Typer 更新明确选择的 Shell 配置，并提示重启终端。
- Run ID 补全以只读 SQLite 查询完成，超时很短；`status/logs` 包含所有 Run，`attach/cancel` 仅活动 Run。

## 本地文件、环境变量与权限

默认位置遵循 macOS Library 目录或 Linux XDG；用以下命令查看实际值：

```bash
runbuoy config path
```

测试、隔离或便携运行可设置：

- `RUNBUOY_HOME`：统一重定向 config/data/state/cache。
- `RUNBUOY_SOCKET_DIR`：重定向短 Unix Socket 目录。
- `RUNBUOY_DISABLE_KEYRING=1`：强制 mode `0600` 凭证文件。
- `XDG_CONFIG_HOME`、`XDG_DATA_HOME`、`XDG_STATE_HOME`、`XDG_CACHE_HOME`。

目录使用 `0700`；config、credential fallback、manifest、log、result 使用 `0600`。
Darwin 的 Unix Socket 路径较短，因此默认在 `/tmp/runbuoy-<uid>/` 下建立 owner-only 目录。

Worker 为目标注入：

- `RUNBUOY_RUN_ID`
- `RUNBUOY_EVENT_SOCKET`
- `RUNBUOY_EVENT_TOKEN`

Token 只用于该 Run 的本地事件 Socket，不是 Server credential。

## 网络故障行为

- 事件在本地事务提交后才尝试上传。
- uploader 默认每 0.25 秒唤醒，批量最多 100；关键状态会主动唤醒。
- HTTP 失败按 1、2、4…秒指数退避，上限 60 秒；执行继续。
- terminal 事件在 Worker 退出前尽力完整 drain。
- Server 不可达会让 iPhone 状态延迟，不会改变目标命令或凭空宣告失败。
