# RunBuoy 文档索引

文档按用途和受众分类：产品目标、用户可见功能、普通用户指南、开发者与自建指南、系统设计和代码来源。

## 推荐阅读路径

- 普通用户：先读[安装指导](user-guide/installation.md)与[功能总览](features/README.md)，使用 Agent 时参考 [Agent Skill 指南](user-guide/agent-skill.md)。
- 开发和设计：先读[架构](design/architecture.md)、[事件协议](developer-guide/event-protocol.md)与[开发指南](developer-guide/development.md)。
- 自建和发布：先读[自托管指南](developer-guide/self-hosting.md)，再按[部署与发布指南](developer-guide/deployment-and-release.md)执行。

## 产品

- [产品需求](product/prd.md)

## 功能事实库

以下文档以当前代码为准，供官网介绍、用户指南和 Agent Skill 编写复用：

- [产品功能总览与当前实现边界](features/README.md)
- [CLI 全命令与用法](features/cli.md)
- [四种进度、阶段、消息与 Python SDK](features/progress-sdk.md)
- [iOS App、通知与 Live Activity](features/ios.md)
- [Server、推送、事件协议、自托管与 Webhook](features/server.md)

## 设计

- [架构](design/architecture.md)
- [安全与隐私](design/security.md)
- [威胁模型](design/threat-model.md)
- [单向只读 ADR](design/adr/0001-one-way-read-only-architecture.md)

## 用户指南

- [安装、更新、项目 API 与配对](user-guide/installation.md)
- [Agent Skill 编写参考](user-guide/agent-skill.md)

## 开发者与自建指南

- [开发与测试](developer-guide/development.md)
- [事件协议](developer-guide/event-protocol.md)
- [自托管](developer-guide/self-hosting.md)
- [APNs 配置](developer-guide/apns-setup.md)
- [iOS 签名](developer-guide/ios-signing.md)
- [CLI 分发与 PyPI 发布](developer-guide/cli-distribution.md)
- [官网内容、双语维护、构建与发布](developer-guide/website-maintenance.md)
- [部署与发布](developer-guide/deployment-and-release.md)

## 代码来源

- [代码来源与第三方材料](code-provenance.md)
