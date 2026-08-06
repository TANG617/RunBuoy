---
description: 使用一条可复制的安全提示词，让支持 Skill 的 Agent 安装并验证 RunBuoy Skill 与 CLI。
---

# 使用 Agent 安装 RunBuoy

这条产品无关的提示词会让 Agent 安装 RunBuoy Skill，再按照 Skill 自带的安全规则检测、安装并验证 CLI。它不会启动配对、Demo 或任何被监控命令。

## 前置条件

- Agent 支持从源码安装或导入 Skill；具体机制由 Agent 自己决定。
- 电脑运行 macOS 或 Linux；RunBuoy 本地运行需要 Python 3.12+ 与 `tmux`。
- 如果缺少 `uv` 或 `tmux`，Agent 会先说明需要执行的系统命令并等待确认。

Skill 源码位于 [GitHub 上的 `skills/runbuoy`](https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy)，必须完整保留 `SKILL.md`、`agents/openai.yaml` 和 `references/` 目录。

## 复制完整安装提示词

复制下面整段提示词并粘贴给支持 Skill 的 Agent：

```text
请帮我安装并验证 RunBuoy：

1. 使用你原生支持的 Skill 安装机制，从
https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy
安装 RunBuoy Skill，完整保留 SKILL.md、agents/openai.yaml 和 references/ 目录，不要猜测安装路径。

2. 安装后读取该 Skill 的 references/installation.md，并按照其中的安全规则安装 RunBuoy CLI。先检查 command -v runbuoy；如果缺失且 uv 已可用，执行：
uv tool install --python 3.12 runbuoy

3. 如果缺少 uv、tmux，或者需要 sudo、系统包管理器或 curl 安装器，请先说明将执行的命令并等待我的确认。

4. 最后运行：
runbuoy --version
runbuoy doctor --json
runbuoy capabilities --json

只汇报 Skill 是否能以 $runbuoy 被发现、CLI 版本、local_ready 和 delivery 状态。不要启动配对、Demo、被监控命令，也不要上传日志。
```

提示词不写死任何 Agent 产品的安装目录，因此可以交给 Codex 或其他支持 Skill 的 Agent。若 Agent 不支持安装 Skill，它应说明自身支持的手动方式，而不是猜测安装路径。

## 安全边界

- 已安装的 CLI 会先被检测，不会重复安装。
- `sudo`、系统包管理器与 curl 安装器都需要先获得你的确认。
- 验证阶段只读取版本、`local_ready` 与 `delivery` 状态。
- 安装过程不配对 iPhone、不运行 Demo、不启动被监控命令，也不上传日志。

## 安装后使用

在支持 Skill 调用的对话中，可以使用现有默认文案：

```text
Use $runbuoy to monitor this command safely from my iPhone.
```

然后在同一条请求中提供需要运行的完整命令。Agent 应先执行 RunBuoy 预检，保留 `--` 后的原命令，并且除非你明确要求，不上传完整日志或共享日志尾部。
