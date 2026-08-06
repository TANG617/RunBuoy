---
description: 使用 Python SDK、runbuoy emit、行匹配或正则表达式向 RunBuoy 提供真实进度。
---

# 进度模式

RunBuoy 只展示命令真实提供的进度，从不根据已用时间推测百分比或 ETA。

## 结构化进度

CLI 的 `uv tool` 环境与项目环境隔离。程序使用 Python SDK 前，先在项目根目录声明依赖：

```bash
uv add --optional runbuoy runbuoy
uv sync --extra runbuoy
```

然后在代码中调用：

```python
from runbuoy import get_reporter

reporter = get_reporter()
reporter.progress(
    current=37,
    total=100,
    phase="processing",
    message="Processing item 37",
)
```

这些调用必须运行在 RunBuoy 启动的目标进程树内，才能读取 Worker 注入的本地 Socket 与临时 Token：

```bash
runbuoy run --progress structured -- uv run --extra runbuoy python experiment.py
```

如果无法修改项目依赖，可以从 RunBuoy 启动的子进程发送等价事件：

```bash
runbuoy emit progress \
  --current 37 \
  --total 100 \
  --phase processing \
  --message "Processing item 37"
```

Reporter 方法默认 best-effort：没有 RunBuoy 上下文或本地 Worker 失败时返回 `False`，业务继续执行。返回 `True` 只确认本地 Worker 接受，不表示 Server 或 iPhone 已收到。

## 行匹配

当每一行代表一个有界工作单元：

```bash
runbuoy run \
  --progress lines \
  --total 100 \
  --match '^Hello World$' \
  -- python3 script.py
```

## 正则进度

当输出包含稳定的当前值与总量：

```bash
runbuoy run \
  --progress regex \
  --pattern '^PROGRESS: ([0-9]+)/([0-9]+)$' \
  -- python3 experiment.py
```

被 lines/regex 匹配接受的记录会成为最新脱敏消息，并可能远端可见。structured phase/message/attention 和显式日志 tail 也可能远端可见；脱敏不等于可以披露敏感输出。

## 不确定进度

没有真实进度源时，不添加进度参数即可。iPhone 会显示运行状态、阶段、已用时间与最后更新时间，而不是虚构百分比。
