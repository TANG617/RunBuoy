# 进度模式

RunBuoy 只展示命令真实提供的进度，从不根据已用时间推测百分比或 ETA。

## 结构化进度

程序可以直接使用 Python SDK：

```python
from runbuoy import progress

progress(
    current=37,
    total=100,
    phase="processing",
    message="Processing item 37",
)
```

也可以从子进程发送事件：

```bash
runbuoy emit progress \
  --current 37 \
  --total 100 \
  --phase processing \
  --message "Processing item 37"
```

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

## 不确定进度

没有真实进度源时，不添加进度参数即可。iPhone 会显示运行状态、阶段、已用时间与最后更新时间，而不是虚构百分比。
