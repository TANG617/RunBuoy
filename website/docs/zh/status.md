---
title: 服务状态
description: RunBuoy Global 服务与自托管部署的状态定义和事件渠道。
---

# 服务状态

RunBuoy 目前不公布 uptime 百分比，也没有历史状态面板。本页只说明可观察的服务端点和事件渠道，不表示你阅读时服务一定正常。

## Global 服务

托管 API 基础地址是 `https://api.runbuoy.cloud`。

| 检查 | 含义 | 不保证的事项 |
| --- | --- | --- |
| [`/healthz`](https://api.runbuoy.cloud/healthz) | API 进程可以响应，并返回其配置的区域。 | 数据库就绪、队列处理、推送送达或端到端可用性。 |
| [`/readyz`](https://api.runbuoy.cloud/readyz) | API 报告请求所需的应用依赖和迁移已经就绪。 | APNs 送达、特定设备连接或未来可用性。 |

HTTP 错误、超时或就绪组件失败是有用的诊断信号，但不是完整的事件判断。疑似 Global 服务事件请通过 [GitHub Issue](https://github.com/TANG617/RunBuoy/issues) 报告，并移除令牌、配对码和私密 Run 数据。

安全事件应使用 [GitHub 私密漏洞报告](https://github.com/TANG617/RunBuoy/security/advisories/new)，不要提交公开 Issue。

## 自托管部署

自托管实例不会继承 Global 服务状态。运营者应自行监控 `/healthz`、`/readyz`、数据库、Worker、APNs 配置、存储、备份和保留任务。部署边界请参阅[自托管指南](/self-hosting)。
