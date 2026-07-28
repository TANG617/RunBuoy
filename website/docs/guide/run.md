# 运行与通知

## 运行命令

把原命令完整放在 `--` 后面：

```bash
runbuoy run -- python3 experiment.py
```

RunBuoy 会保留原命令的退出码，在本地镜像输出，并发送安全的状态投影。

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

## 本地命令

以下操作只读取或控制当前电脑：

```bash
runbuoy list
runbuoy status RUN_ID
runbuoy logs RUN_ID
runbuoy attach RUN_ID
runbuoy cancel RUN_ID
```

iPhone 和服务器都不能调用这些命令。

## 可选安全日志片段

完整日志始终留在本地。需要时可以明确上传最多 100 行、经过脱敏的末尾片段：

```bash
runbuoy run --share-log-tail 20 -- command
```

上传片段会在 iOS 中明确标注，并最多保留 24 小时。
