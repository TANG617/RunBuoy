# 自托管

RunBuoy Server 可以部署在自己的基础设施中。

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

## 生产注意事项

- 不要把 PostgreSQL 暴露到公网。
- 在可信入口终止 TLS，只转发 API 端口。
- 独立生成数据库、凭证哈希和 Token 加密密钥。
- 将 APNs `.p8` 文件存放在 Secret Store。
- 数据库与 Token 加密密钥必须配套备份。
- 明确共享的日志片段应在 24 小时内删除。

完整部署说明见 [docs/self-hosting.md](https://github.com/TANG617/RunBuoy/blob/main/docs/self-hosting.md)。
