---
description: 部署自有 RunBuoy Server，并确保 CLI 与自有 iOS 构建在配对前连接同一服务。
---

# 自托管

RunBuoy Server 可以部署在自己的基础设施中。

:::warning 配对前必须统一 Server
CLI 与自有 iOS 构建必须在配对前指向同一个 RunBuoy Server。CLI 使用 `runbuoy config set --server-url`，App 构建必须把 `RUNBUOY_API_BASE_URL` 设置为同一个 HTTPS 地址；配对后不能把已有 Machine 直接迁移到另一 Server。当前官方端到端流程使用 `Global` 区域。
:::

## 要求

- Docker Engine 与 Docker Compose
- HTTPS 域名和反向代理或负载均衡器
- PostgreSQL 与可靠备份
- 随机数据库密码、凭证 Pepper 和 Token 加密密钥
- 生产推送所需的 Apple APNs 凭证

## Mock 模式

在仓库根目录执行：

```bash
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build
```

Mock APNs 不需要 Apple 凭证，会记录确定性的推送载荷，适合开发与端到端测试。

## 配置 CLI

```bash
runbuoy config set --server-url https://runbuoy.example.com
runbuoy doctor
```

同时在自有 iOS 构建中设置：

```text
RUNBUOY_API_BASE_URL=https://runbuoy.example.com
```

当前 App 没有供用户输入自托管地址的设置界面，因此仅修改 CLI 不足以完成自托管配对。

## 生产注意事项

- 不要把 PostgreSQL 暴露到公网。
- 在可信入口终止 TLS，只转发 API 端口。
- 独立生成数据库、凭证哈希和 Token 加密密钥。
- 将 APNs `.p8` 文件存放在 Secret Store。
- 数据库与 Token 加密密钥必须配套备份。
- 明确共享的日志片段应在 24 小时内删除。

完整部署说明见 [docs/developer-guide/self-hosting.md](https://github.com/TANG617/RunBuoy/blob/main/docs/developer-guide/self-hosting.md)。
