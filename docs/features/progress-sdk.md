# 进度、阶段、消息与 Python SDK

RunBuoy 的原则是：只展示命令真实暴露的进度，不从耗时猜百分比或 ETA。CLI 的解析实现在
[`progress_adapters.py`](../../cli/src/runbuoy/progress_adapters.py)，Python API 实现在
[`sdk.py`](../../cli/src/runbuoy/sdk.py)。

## Python 包可用性

`runbuoy` distribution 是 CLI、Worker 和 Python API 的唯一实现。仓库不再维护 import 名冲突的第二份
轻量 SDK。

`uv tool install runbuoy`/`pipx install runbuoy` 会把 CLI 放在隔离环境中，**不会**自动让目标项目使用的
`python3` 能 `import runbuoy`。已发布的 `runbuoy` wheel 本身同时包含 CLI 和 Python API，因此推荐在
目标项目中把同一个 distribution 声明为名为 `runbuoy` 的**可选 extra**，让默认业务环境不依赖
RunBuoy：

```bash
uv tool install --python 3.12 runbuoy

cd my-project
uv add --optional runbuoy runbuoy
uv sync --extra runbuoy
```

requirements 项目使用独立的 `requirements-runbuoy.txt`，不修改默认 requirements。无法修改项目依赖时，
可使用随 CLI 安装的 `runbuoy emit` 子命令，不需要让目标 Python import API。

完整安装、更新和配对步骤见[安装指导](../user-guide/installation.md)。

## 选择模式

| 命令已有的信号 | 应选模式 | 理由 |
| --- | --- | --- |
| 已调用 RunBuoy SDK，或能在代码/子进程中执行 `runbuoy emit` | `structured` | 语义最明确，可同时上报 current/total、阶段和消息 |
| stdout/PTY 中已有稳定的 `current/total` 记录 | `regex` | 不需要改目标程序 |
| 每个完成单元会输出一条可识别记录，并且已知总数 | `lines` | 以真实完成单元计数 |
| 没有真实 current/total | `indeterminate` | 不制造百分比 |

Agent 不应仅根据“已经运行了多久”选择一个虚构 total，也不应把日志行数当作进度，除非每行确实
代表一个有界完成单元。

## 不确定进度

```bash
runbuoy run --progress indeterminate -- command
# 也是默认值
runbuoy run -- command
```

不解析输出，不产生 determinate progress。iOS 仍会显示执行状态、阶段（若另行上报）、最近安全消息、
电脑确认的运行时长和最后更新时间。

## 结构化进度：Python API

推荐取得一个可注入业务边界的 Reporter：

```python
from runbuoy import get_reporter

reporter = get_reporter(required=False, on_error=None)
accepted_locally = reporter.progress(
    current=37,
    total=100,
    unit="items",
    phase="processing",
    message="Processing item 37",
)
reporter.phase("validating")
reporter.message("Waiting for the final artifact")
reporter.attention("Human review is needed", status="ACTION_REQUIRED")
```

`reporter.enabled` 表示当前进程发现了本地 Worker 上下文。方法返回 `True` 只表示**本地 Worker 已接受
事件**，不表示 Server 已接受，更不表示 iPhone 已送达。

推荐启动方式：

```bash
runbuoy run \
  --title "Dataset import" \
  --progress structured \
  -- python3 import.py
```

### Reporter 与函数语义

`get_reporter(required=False, on_error=None)` 默认 best-effort：

- 没有 RunBuoy 环境时 `enabled=False`，所有方法返回 `False`，不调用 error callback；
- Socket、协议、校验、Worker 拒绝或 SDK 内部失败时返回 `False`、线程安全地禁用 Reporter，并最多调用一次
  `on_error`；
- callback 自身异常会被吞掉；SDK 不自动写 stderr 或 logging；
- `required=True` 对相同失败抛类型化异常，适合严格集成测试，不适合默认业务路径。

公开异常为 `RunBuoyUnavailableError`、`RunBuoyRejectedError`、`RunBuoyProtocolError`、
`RunBuoyValidationError`、`RunBuoyInternalError`，共同继承 `RunBuoyError`。

顶层 `progress`、`phase`、`message`、`attention` 委托给默认 best-effort Reporter，也返回 `bool`。

#### `progress(current, total, *, unit=None, phase=None, message=None)`

- current/total 接受数字；total 必须 > 0。
- current 小于 0 时投影为 0，大于 total 时投影为 total。
- 同一个 Worker 内的显式 current 不能倒退；倒退请求返回 `stale_progress`。
- fraction 由 Worker 计算为 clamped current / total。
- source 为 `explicit`。
- phase 最多 120 字符；message 最多 500 字符并脱敏。

#### `phase(value)`

生成 `run.phase_changed`，更新 Run 当前阶段。阶段是安全的用户可见字符串；不要放路径、客户数据或 secret。

#### `message(value)`

生成 `run.message`，更新当前安全消息。它不是日志通道，不适合频繁或大量输出。

#### `attention(value, *, status="ACTION_REQUIRED")`

生成 `run.attention_required`。合法 status：

- `INFORMATION`
- `WARNING`
- `ACTION_REQUIRED`

当前 CLI/SDK 没有把 attention 恢复为 `NONE` 的公开命令；状态会保留在后续投影中。因此仅在确实需要突出时使用。

### 运行环境要求

Worker 为目标和其子进程继承以下变量：

```text
RUNBUOY_RUN_ID
RUNBUOY_EVENT_SOCKET
RUNBUOY_EVENT_TOKEN
```

SDK 通过 Unix Socket 发送单行 JSON，并用每个 Run 独有的临时 Token 鉴权。Socket mode 为 `0600`，
单请求上限约 64 KiB，客户端超时 2 秒。它不连接 Server，也不包含 APNs 或长期 Machine credential。

在普通 Shell、Notebook 或不由 RunBuoy 启动的进程中，默认 Reporter 静默禁用，业务代码继续运行。
不要伪造环境变量。严格调用 `get_reporter(required=True)` 会抛 `RunBuoyUnavailableError`。

若项目允许完全不安装 RunBuoy，fallback 只能捕获 `ModuleNotFoundError` 且验证
`error.name == "runbuoy"`；不能用宽泛 `ImportError` 隐藏 RunBuoy 内部依赖损坏。完整同签名
`NoopReporter` 模板见 [Agent Skill 参考](../user-guide/agent-skill.md)。

## 结构化进度：CLI 子命令

当 Bash/Makefile 或子进程不方便导入 Python：

```bash
runbuoy emit progress \
  --current 37 \
  --total 100 \
  --unit items \
  --phase processing \
  --message "Processing item 37"

runbuoy emit phase "validating"
runbuoy emit message "Waiting for artifact"
runbuoy emit attention "Review required" --status WARNING
```

`runbuoy emit` 必须在目标进程树中执行并能找到同一 CLI。它返回前会等待本地 Worker 接受事件，
但不等待事件送达 Server 或 iPhone。

实现层会为所有 Run 启动 Event Socket，因此即使选择 `lines`、`regex` 或默认模式，phase/message/attention
仍能工作，显式 progress 也不会被强制拒绝。不过同时使用多个进度来源会让最后到达的进度互相覆盖；
公开集成应在需要显式 progress 时选择 `structured`，避免混合来源。

## 行计数进度

```bash
runbuoy run \
  --progress lines \
  --total 100 \
  --match '^DONE$' \
  --unit items \
  -- python3 batch.py
```

行为：

- `--total` 必须 > 0。
- `--match` 是 Python 正则，对去 ANSI、trim 后的每条终端记录做 `search`；省略则每条非空记录都计数。
- 同时识别 LF、CR 和 CRLF，能处理 UTF-8 被拆分到多个读取块的情况。
- 终端程序常用 `\r` 原地刷新；相同的连续 CR 记录会去重，普通换行的相同文本仍分别计数。
- current 每次 +1，并在 total 处封顶。
- 每次匹配记录同时成为脱敏后的最新 safe message。
- 默认 unit 为 `lines`；传 `--unit` 可覆盖。
- source 为 `lines`。

适合：固定数量测试、文件、分片或样本，并且每个完成单元有明确输出。
不适合：无界日志、重试会重复打印、单元数动态变化、每个单元打印多行。

## 正则 current/total 进度

```bash
runbuoy run \
  --progress regex \
  --pattern '^PROGRESS: ([0-9]+)/([0-9]+)$' \
  --unit items \
  -- python3 experiment.py
```

行为：

- pattern 必须至少有两个捕获组。
- group 1 和 group 2 必须能转成 float。
- total <= 0 的记录被忽略。
- current 小于上次接受值的记录被忽略。
- clamp 后 current 与上次相同的记录被忽略。
- current > total 会显示为 100%，不会显示超过 100%。
- 匹配的完整记录会成为脱敏后的 safe message。
- 能处理 ANSI、CR 进度条、UTF-8 和跨读取块记录。
- source 为 `regex`。

建议 pattern 锚定一条专用进度记录，避免误匹配业务数字。若程序可能更换 total，要保证 current 的含义仍单调；
适配器只用 current 判断倒退，不会验证 total 是否恒定。

## 进度显示语义

确定进度的协议字段：

```json
{
  "kind": "determinate",
  "source": "explicit",
  "current": 37,
  "total": 100,
  "fraction": 0.37,
  "unit": "items",
  "phase": "processing",
  "message": "Processing item 37"
}
```

不确定进度至少包含：

```json
{
  "kind": "indeterminate",
  "source": "unknown"
}
```

当前 CLI 的默认 indeterminate Run 不一定持久化一个 progress 对象；iOS 会把缺少 progress 视为不确定进度。

显示规则：

- CLI `list/status` 把 fraction 限制在 0–100% 后四舍五入为整数百分比。
- iOS 显示百分比、current/total 和 unit；无 fraction 的活动 Run 显示动画不确定进度。
- Widget 显示百分比或“不确定进度”；灵动岛紧凑区域无百分比时显示电脑确认耗时。
- Live Activity 普通 progress 会在 Server 合并；频繁更新允许时最快 1 秒，不允许时至少 15 秒。
- Server 对小于 1% 的连续变化延后；相对上次至少 10% 的 progress 使用高 APNs 优先级。

## 心跳和时间不是进度

Worker 在没有其他限制时每 15 秒发送 `run.heartbeat`。每个事件都证明 Machine → Server 路径在
`occurred_at` 时收到过电脑确认；它不会增加 current 或计算 ETA。

- CLI 本地 status 距最后事件 60 秒后显示 Stale。
- Live Activity 的 stale date 是最后确认时间 + 60 秒。
- Live Activity 显示 `createdAt → updatedAt` 的固定确认时长。若没有新事件，数字冻结，明确反映交付路径没有新确认。
- iOS App 活动列表用 `startedAt → updatedAt` 显示执行时长和相对心跳时间。

“Stale”不等于命令已停止；它只表示尚未收到新的确认。

## 安全消息规则

phase、message、attention 和匹配的输出记录都会成为远端可见文字，应遵守：

- 不放完整命令参数、路径、URL query、客户名、提示词或用户输入；
- 不放 token、password、API key、Authorization header；
- 不把完整日志拆成大量 message 逐条上报；
- 需要日志时仍默认使用本地 `runbuoy logs`；只有用户明确同意才选择 `--share-log-tail`。

内置脱敏会处理 ANSI、Bearer、常见 key/value secret、OpenAI 风格 `sk-...` 和 PEM 私钥块，
但无法识别所有业务敏感内容。

## 示例

### 训练/实验循环

```python
import time
from runbuoy import get_reporter

reporter = get_reporter()
epochs = 20
for epoch in range(1, epochs + 1):
    # train_one_epoch(...)
    reporter.progress(
        epoch,
        epochs,
        unit="epochs",
        phase="training",
        message=f"Epoch {epoch} complete",
    )
    time.sleep(1)
```

```bash
runbuoy run --progress structured --title "Model training" -- python3 train.py
```

### Make/CI 中只上报阶段

```bash
runbuoy run --progress indeterminate -- make release
```

由被监控脚本在适当位置调用：

```bash
runbuoy emit phase "Building"
runbuoy emit message "Artifacts built"
runbuoy emit phase "Signing"
```

### Gurobi 等回调

仅当 solver 能提供有意义的已处理节点和明确上限时才上报 determinate：

```python
from runbuoy import get_reporter

reporter = get_reporter()

def report_solver_progress(nodes_processed: int, node_limit: int, gap: float) -> None:
    reporter.progress(
        nodes_processed,
        node_limit,
        unit="nodes",
        phase="optimizing",
        message=f"Solver gap {gap:.2%}",
    )
```

若 `node_limit` 不是任务总量或会动态变化，应使用 indeterminate + phase/message，避免制造误导。
