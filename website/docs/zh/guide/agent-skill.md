---
description: 使用可复制的通用 Agent 提示词安装 RunBuoy Skill，并在安装后以 $runbuoy 安全监控命令。
---

# 安装 Agent Skill

RunBuoy Skill 为支持原生 Skill 机制的 AI Agent 提供预检、启动、查看与隐私边界说明。它不会替代 RunBuoy CLI。

## 前置条件

- Agent 支持从源码安装或导入 Skill；具体机制由 Agent 自己决定。
- 电脑上已经安装并可执行 `runbuoy` CLI。
- 安装时只复制 Skill 文件，不启动配对、Demo 或被监控命令。

Skill 源码位于 [GitHub 上的 `skills/runbuoy`](https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy)，必须完整保留 `SKILL.md`、`agents/openai.yaml` 和 `references/` 目录。

## 交给 Agent 安装

复制下面整段提示词并粘贴给支持 Skill 的 Agent：

```text
请使用你原生支持的 Skill 安装机制，从 https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy 安装 RunBuoy Skill；完整保留 SKILL.md、agents/openai.yaml 和 references/ 目录，安装时不要启动配对、Demo 或任何被监控命令。安装后只确认该 Skill 能以 $runbuoy 被发现；如果你不支持可安装 Skill，请明确说明支持的手动方式，不要猜测安装路径。
```

代码块自带复制按钮。这个提示词不写死任何 Agent 产品的安装目录，因此可以交给 Codex 或其他支持 Skill 的 Agent。

## 安装后使用

在支持 Skill 调用的对话中，可以使用现有默认文案：

```text
Use $runbuoy to monitor this command safely from my iPhone.
```

然后在同一条请求中提供需要运行的完整命令。Agent 应先执行 RunBuoy 预检，保留 `--` 后的原命令，并且除非你明确要求，不上传完整日志或共享日志尾部。
