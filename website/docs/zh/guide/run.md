# 运行与通知

## 运行命令

把原命令完整放在 `--` 后面：

```bash
runbuoy run -- python3 experiment.py
```

RunBuoy 会保留原命令的退出码，在本地镜像输出，并发送安全的状态投影。
普通启动会立即返回；需要等待并获得原命令退出码时使用：

```bash
runbuoy run --wait -- command
```

指定一个不包含路径、参数或敏感信息的标题：

```bash
runbuoy run \
  --title "Gurobi experiment" \
  -- python3 experiment.py
```

## 发送一次通知

不启动托管 Run，也可以发送状态通知：

```bash
runbuoy notify \
  --title "Build completed" \
  --body "Release build succeeded" \
  --level success
```

也可以使用不需要参数的内置验证：

```bash
runbuoy demo notification
runbuoy demo live-activity
```

## 本地命令

以下操作在当前电脑上执行：

```bash
runbuoy list
runbuoy list -a
runbuoy status RUN_ID
runbuoy logs RUN_ID
runbuoy attach RUN_ID
runbuoy cancel RUN_ID
```

iPhone 和服务器都不能调用这些命令。

`list` 默认只显示正在运行的任务；`-a/--all` 才包含已完成历史。显示时间采用
本地时区并精确到秒。`status`、`logs`、`attach` 与 `cancel` 均支持唯一 Run ID
前缀；`@latest` 表示最近一次 Run。

预览并清理较旧的本地记录与日志：

```bash
runbuoy history prune --older-than 30d --dry-run
runbuoy history prune --older-than 30d
```

清理操作会要求确认，并且不可恢复。
默认不会删除仍有待同步事件的 Run；只有明确使用 `--include-unsynced` 才会同时
丢弃这些事件。

## 预览远端数据

不启动命令也可以检查哪些内容会显示在远端：

```bash
runbuoy run --dry-run --title "Safe title" -- command --secret local-only
runbuoy notify --dry-run --title "Preview" --body "Nothing is sent"
```

## 可选安全日志片段

完整日志始终留在本地。需要时可以明确上传最多 100 行、经过脱敏的末尾片段：

```bash
runbuoy run --share-log-tail 20 -- command
```

上传片段会在 iOS 中明确标注，并最多保留 24 小时。
