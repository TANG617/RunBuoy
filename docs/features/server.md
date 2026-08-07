# Server、推送、协议与 Webhook 功能参考

Server 是只读投影和推送服务，不是执行控制平面。FastAPI 路由以
[`server/app/api.py`](../../server/app/api.py) 为准，投影/推送策略在
[`services.py`](../../server/app/services.py)，APNs worker 在
[`outbox.py`](../../server/app/outbox.py)。机器可读契约位于
[`packages/protocol`](../../packages/protocol)。

## 进程和数据存储

标准部署包含：

- `runbuoy-api` / Uvicorn：HTTP API；
- PostgreSQL：身份、Run、事件、通知、订阅、Activity binding、push outbox/attempt；
- `runbuoy-outbox`：独立 APNs worker 和 retention cleanup；
- Alembic migrations；
- 可选 Caddy HTTPS ingress。

API 对投影变更和 push outbox 做同一数据库事务。PostgreSQL 使用 `pg_notify` 唤醒 worker；
SQLite 开发模式使用短轮询 fallback。不需要 Redis。

## 健康检查

```http
GET /healthz
```

无需鉴权，返回：

```json
{"status":"ok","region":"global"}
```

region 来自 `RUNBUOY_REGION=global|cn`。它只说明 API 进程配置/可达，不验证 APNs 已成功送达。

## 请求限制、限流和资源配额

API 在 FastAPI 解析 body 之前执行有界流读取。默认 request body 上限为 256 KiB；即使请求没有
`Content-Length` 或使用 chunked transfer，累计超过 `MAX_REQUEST_BODY_BYTES` 也会返回 413，且不会进入业务
handler。`/healthz` 和 `/readyz` 不读取无关 request body，因此不受该 middleware 影响。

业务限流使用 PostgreSQL/SQLAlchemy fixed-window bucket 和原子 upsert，多 API worker 共享同一计数；不使用
进程内字典。默认 bucket 为：

| Bucket | 默认值 | Key |
| --- | ---: | --- |
| Device bootstrap | 20/hour | HMAC 匿名 IP |
| Pairing create | 30/hour | HMAC 匿名 IP |
| Pairing status poll | 120/minute | pairing session |
| Run upsert | 120/minute | Machine |
| Event batch | 240/minute | Machine |
| Notification | 60/minute | Machine 或 Hook |
| Webhook Run upsert/event | 240/minute | Hook |

成功响应包含稳定的 `X-RateLimit-Bucket`、`X-RateLimit-Limit`、`X-RateLimit-Remaining` 和
`X-RateLimit-Reset`。超限返回 429，并额外提供 `Retry-After` 和结构化 `rate_limit_exceeded` error。
默认 `RATE_LIMIT_FAIL_OPEN=false`：limiter accounting 失败时返回 503；只有运营方明确接受失去防护的风险时才
可设置为 `true`。worker retention cleanup 会删除已过 reset + retention grace 的 bucket 和闲置 quota lock。

Server 不保存原始 IP。IP key 使用独立的 `RATE_LIMIT_IP_PEPPER` 做 HMAC-SHA256。默认忽略
`X-Forwarded-For`；仅当直连 peer 属于 `TRUSTED_PROXY_CIDRS` 时，才从右向左剥离可信代理并使用第一个不可信
地址。不要把公网 CIDR 加入 trusted proxy 配置，入口代理必须 append 或 sanitize 该 header。

默认资源配额全部可通过环境变量调整：每 Workspace 25 台未撤销 Machine、每 Machine 100 个活动 Run、每
HMAC IP 10 个未 claim 且未过期 pairing session、每 Workspace 50 个未撤销 Webhook、每 Workspace 每 UTC
日 1000 条 Notification，以及每 event batch 100 个事件。资源容量错误返回结构化
`resource_quota_exceeded`；event batch 超限返回结构化 413。配额在应用层按 Workspace/Machine 所有权执行，
数据库行锁避免并发绕过。100-event batch 与 240 batches/minute 允许合法 offline outbox 高速恢复，15 秒
heartbeat 仅占每分钟 4 个事件。

生产 Compose 将 Caddy 固定在专用容器地址并只信任该地址追加的转发链，同时对公网 `/metrics` 返回 404；监控
应从私有 API/Compose 网络采集。Caddy 可继续负责 TLS、连接数和基础传输保护；request ownership、业务
bucket 和资源配额必须由 App 层执行，不依赖定制 Caddy 插件。

## 身份、凭证和 Scope

### Device credential

由 iOS bootstrap 获得，默认 scopes：

```text
runs:read
machines:read
notifications:read
devices:register-token
live-activities:register-token
pairing:claim
preferences:write
subscriptions:delete
```

Device 能读取投影、注册自己的接收 token、claim pairing、改自己的接收偏好、删除自己的 subscription。
它还可以重置自己的接收身份、撤销同 Workspace 的 Machine，以及通过短期 challenge 删除自己的匿名
Workspace。这些都是身份/接收平面操作，不会向 Machine 发送指令。
不能创建 Run、写事件、发机器通知或改 Machine 名。

### Machine credential

由一次性 pairing exchange 获得，默认 scopes：

```text
runs:create
runs:update
events:write
notifications:send
hooks:manage
machines:update
pairing:poll
```

Machine 能写自己的 Run/事件/通知/名字和管理 Hook，不能读取 Device Run 列表或 APNs token。
Machine 可用自己的 bearer 调用 `revoke-self`；成功后该 bearer 和它创建的 Hook bearer 都失效。

### Webhook credential

每个 Hook 有独立 bearer secret，只能调用该 Hook URL。Server 只保存带 pepper 的哈希。

### 存储规则

- Device/Machine/Webhook 长期 bearer 只保存哈希。
- Pairing exchange secret 只保存哈希。
- APNs notification、push-to-start、Activity update token 用 Fernet 加密保存。
- Token 不通过读 API 返回。

## API 功能表

| 方法和路径 | 调用者 | 功能 |
| --- | --- | --- |
| `POST /v1/devices/bootstrap` | 匿名 iOS | 仅创建新的 Device/Workspace；重复 installation ID 返回 409，不具备 credential 恢复能力 |
| `PUT /v1/devices/{id}/notification-token` | owner Device | 注册普通 APNs token，支持 generation |
| `PUT /v1/devices/{id}/push-to-start-token` | owner Device | 注册 ActivityKit push-to-start token |
| `POST /v1/devices/{id}/activity-sync` | owner Device | 同步当前 Activity lifecycle、sequence、token 和 frequent push 设置 |
| `PUT /v1/live-activities/{activity_id}/update-token` | owner Device | 注册/轮换某 Activity update token |
| `PATCH /v1/device-preferences` | Device | 修改 Live Activity、成功/失败通知接收偏好 |
| `DELETE /v1/machine-subscriptions/{id}` | owner Device | 停止该 Device 接收某 Machine |
| `DELETE /v1/devices/{id}` | owner Device | 重置本 Device credential、tokens、subscriptions、bindings 和 pending push |
| `POST /v1/machines/{id}/revoke` | owner Device | 撤销同 Workspace Machine/Hook credentials 并停止后续接收 |
| `POST /v1/machines/{id}/revoke-self` | owner Machine | CLI unpair 使用；撤销自己的 Server credential |
| `POST /v1/workspaces/{id}/deletion-challenge` | owner Device | 创建绑定 Device/Workspace 的短期、单次删除 challenge |
| `DELETE /v1/workspaces/{id}` | owner Device | challenge 验证后事务删除整个匿名 Workspace 云端数据 |
| `POST /v1/pairing-sessions` | 匿名 Machine pre-pair | 创建短期配对 session |
| `GET /v1/pairing-sessions/{id}` | exchange secret | 轮询 pending/claimed/exchanged |
| `POST /v1/pairing-sessions/{id}/claim` | Device | 用 challenge claim Machine 到自己的 Workspace |
| `POST /v1/pairing-sessions/{id}/exchange` | exchange secret | 一次性换取 Machine credential |
| `PUT /v1/runs/{uuid}` | owner Machine | 注册 Run 安全 metadata |
| `POST /v1/runs/{uuid}/events:batch` | owner Machine | 按序批量写 1–100 个事件 |
| `GET /v1/runs` | Device | 读取 Workspace 最近最多 200 个 Run |
| `GET /v1/runs/{uuid}` | Device | 读取 snapshot 和最多 500 个按序事件 |
| `GET /v1/machines` | Device | 读取 Workspace computers 和本 Device subscription |
| `PATCH /v1/machines/{id}` | owner Machine | 修改 canonical display name，并更新活动 Live Activity |
| `GET /v1/notifications` | Device | 最近最多 200 条 Rich Message |
| `POST /v1/notifications` | Machine | 发送通知，支持 Idempotency-Key |
| `POST /v1/webhooks` | Machine | 创建 Hook，secret 只返回一次 |
| `DELETE /v1/webhooks/{id}` | owner Machine | 撤销 Hook |
| `POST /v1/hooks/{id}/notifications` | Hook bearer | Hook 发送通知 |
| `PUT /v1/hooks/{id}/runs/{external_id}` | Hook bearer | 创建/更新外部 Run |
| `POST /v1/hooks/{id}/runs/{external_id}/events` | Hook bearer | 向外部 Run 追加一个事件 |

代码中没有任何 cancel、retry、execute、signal、input、approve、terminal、command 或 WebSocket route。

## 身份和数据生命周期

“Stop receiving”只删除当前 Device 与该 Machine 的 subscription，并取消已经排队、但尚未发送给该
Device 的相关 push；Machine、Machine credential 和历史 Runs 保持不变。

“Revoke computer”会撤销 Machine 及其 Webhook bearer、删除所有 subscriptions、invalidate 相关
Activity bindings 并取消 pending push。它不会删除历史 Runs，也不会向 Machine 建立消息或控制通道。
Machine 的下一个上传会收到 401。已撤销的固定 machine ID 可以在同一个 Workspace 重新配对。

“Reset this iPhone”撤销当前 Device bearer、清除 APNs/push-to-start tokens、invalidate Activity
bindings、删除 subscriptions 并取消目标 pending outbox。Server 成功后，iOS 才应清理 Keychain、cache
和相关 UserDefaults；Server 失败时应保留本地身份，除非用户明确选择 local-only reset。

Workspace 删除分两步：先提交字面确认 `DELETE` 换取 `rbdc_...` challenge，再在默认 300 秒内把
challenge 放在 DELETE JSON body 中。challenge 不放在 URL，按 Device/Workspace 绑定，后一次创建会
使前一次失效。最终删除在单一数据库事务中完成，包括所有 bearer、Machines、Devices、Runs、事件、
通知、Webhooks、bindings、outbox/attempts、challenge 和该 Workspace audit rows。

## Retention cleanup

Worker 每轮最多按 `RETENTION_CLEANUP_BATCH_SIZE` 处理每类数据，并由索引支持。清理可安全重复：精确位于
cutoff 的数据留到下一轮；active Run 不删；仍有 active/stale Live Activity binding 的终态 Run 不删；
pending outbox 不按 terminal retention 清理。旧 Run 删除时，其依赖事件、终态 push 数据和非活动 binding
在同一事务处理，仍在独立 notification retention 内的消息只解除 Run FK。

| 环境变量 | 默认值 | 含义 |
| --- | ---: | --- |
| `EVENT_RETENTION_HOURS` | 24 | 终态 Run events |
| `RUN_RETENTION_DAYS` | 30 | 无活动 Live Activity 的终态 Runs |
| `NOTIFICATION_RETENTION_DAYS` | 30 | 非 active Run notifications |
| `PUSH_ATTEMPT_RETENTION_DAYS` | 7 | APNs attempts |
| `OUTBOX_TERMINAL_RETENTION_DAYS` | 7 | sent/cancelled/failed/expired/suppressed outbox |
| `PAIRING_RETENTION_HOURS` | 24 | 已过期 pairing sessions 之后的保留窗口 |
| `AUDIT_RETENTION_DAYS` | 90 | lifecycle audit metadata |
| `SAFE_LOG_TAIL_RETENTION_HOURS` | 24 | opt-in safe log tail；过期后写 SQL NULL |
| `RETENTION_CLEANUP_BATCH_SIZE` | 500 | 每类每轮最大处理行数 |
| `WORKSPACE_DELETION_CHALLENGE_TTL_SECONDS` | 300 | Workspace 删除 challenge 有效期 |

## 配对协议

### 1. Machine 创建会话

```http
POST /v1/pairing-sessions
Content-Type: application/json

{
  "machine_id": "machine_...",
  "display_name": "Build Mac",
  "platform": "darwin",
  "architecture": "arm64",
  "cli_version": "0.1.3"
}
```

返回 session ID、随机 challenge、六位 short code、一次性 exchange secret、expires_at。
默认 TTL 300 秒。

### 2. Device claim

iOS 扫描/粘贴 QR，核对电脑和区域后：

```http
POST /v1/pairing-sessions/{session_id}/claim
Authorization: Bearer DEVICE_CREDENTIAL

{"challenge":"..."}
```

Server 创建 Machine 和 MachineDeviceSubscription。session 已 claim、已过期、challenge 不匹配或 Machine ID
已存在都会拒绝。

### 3. Machine exchange

```http
POST /v1/pairing-sessions/{session_id}/exchange

{"exchange_secret":"..."}
```

只有已 claim 且未 exchange 的 session 成功，返回 Machine credential。exchange 不可重放。

## Run 注册和事件协议

### 注册 metadata

```http
PUT /v1/runs/{uuid}
Authorization: Bearer MACHINE_CREDENTIAL

{
  "machine_id": "machine_...",
  "title": "Release build",
  "source": "cli",
  "cli_version": "0.1.3",
  "live_activity_policy": "automatic"
}
```

PUT 只建立安全 metadata。即使 body 带 execution/progress，CLI 路径中真正的执行投影权威仍是 ordered events，
以支持完整离线 CREATED→terminal 重放。

### 事件结构

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "run_id": "uuid",
  "machine_id": "machine_...",
  "seq": 3,
  "type": "run.progress",
  "occurred_at": "2026-08-06T12:00:00Z",
  "payload": {
    "progress": {
      "kind": "determinate",
      "source": "explicit",
      "current": 37,
      "total": 100,
      "fraction": 0.37,
      "unit": "items"
    },
    "phase": "processing",
    "message": "Item 37 complete"
  }
}
```

### 合法事件

```text
run.created
run.starting
run.started
run.progress
run.phase_changed
run.message
run.attention_required
run.heartbeat
run.succeeded
run.failed
run.cancelled
run.lost
```

### 顺序和幂等

- seq 从 1 开始且每个 Run 单调增加。
- batch 1–100，batch 内 event_id 和 seq 各自唯一。
- Server 按 seq 排序处理。
- 同 event_id + 同 run/seq/type 重放是成功 duplicate。
- event_id 重用但内容/位置不同、同 seq 不同事件、seq ≤ last_seq 的新事件均 409。
- 所有权不匹配 403。
- payload 最多 64 KiB；safe log tail 最多 100 行，每行最多 500 字符。
- 未知对象字段忽略；未知 event type 需更高协议版本，会被验证拒绝。

### 状态转换

```text
CREATED  → CREATED | STARTING | RUNNING | terminal
STARTING → STARTING | RUNNING | terminal
RUNNING  → RUNNING | terminal
terminal = SUCCEEDED | FAILED | CANCELLED | LOST
```

终态不可变，终态后任何新事件拒绝。Server 不从 APNs 成败改变 execution status。

### 时间

- `created_at` 取 `run.created.occurred_at`。
- `started_at` 取首次 starting/started 的 Machine 时间。
- `updated_at` 是已接受事件 occurred_at 的单调最大值，即使之后收到一个较早时间戳也不回退。
- `ended_at` 取终态事件时间。
- Server 另存 `received_at`，用于 retention 和运维。

## Read API 投影

Run snapshot 包含：

```text
id, workspace_id, machine_id, machine_name, title, source
execution_status, health_status, attention_status
progress, phase, safe_message, safe_log_tail
created_at, started_at, updated_at, ended_at
exit_code, termination_reason, sequence/last_seq
```

Server 使用 Machine 的当前 canonical name，因此改名后新读请求和后续 Live Activity 都使用新名称。

Server 当前不会根据墙钟自动把 `health_status` 从 HEALTHY 改为 STALE/OFFLINE；stale 主要通过 Live Activity
stale date 和 CLI 本地 status 判定表达。外部 API/Webhook 若写 health 值，iOS 会展示它。

## 普通通知 API

Machine API：

```http
POST /v1/notifications
Authorization: Bearer MACHINE_CREDENTIAL
Idempotency-Key: build-123

{
  "title": "Build completed",
  "subtitle": "Release",
  "body": "Release build succeeded",
  "level": "success",
  "fields": [
    {"label":"Target","value":"iOS"}
  ],
  "safe_link": "https://example.com/build/123",
  "run_id": "optional-run-id",
  "expires_at": "2026-08-07T00:00:00Z"
}
```

限制：title 200、subtitle 200、body 2000、最多 20 fields，label 80、value 500；safe_link 必须 HTTPS。

- Machine Idempotency-Key 在同 Machine 下去重，重复返回同 notification ID，不重复 outbox。
- Hook 通知的 key 在同 Hook 下去重。
- 通知记录写入 Workspace Read API。
- level=`success` 时遵守 Device success 偏好；level=`error` 遵守 failure 偏好。
- `info` 和 `warning` 当前不受这两个布尔偏好过滤。
- APNs alert 只包含 title/body/可选 subtitle；fields/safe_link 不进入普通 push payload，App 打开后从 Read API 获取 fields。
- 当前 iOS 不消费 safe_link。

## Webhook 集成

### 创建和撤销

```http
POST /v1/webhooks
Authorization: Bearer MACHINE_CREDENTIAL

{"name":"CI production"}
```

返回：

```json
{"hook_id":"hook_...","secret":"rbh_..."}
```

secret 只返回一次，应存入 CI Secret Store。撤销：

```http
DELETE /v1/webhooks/{hook_id}
Authorization: Bearer MACHINE_CREDENTIAL
```

当前 CLI 没有管理 Hook 的命令；调用者必须在受控集成中持有合适的 Machine credential。

### Hook 通知

```bash
curl --fail-with-body \
  -H "Authorization: Bearer $RUNBUOY_HOOK_SECRET" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: build-123" \
  -d '{"title":"Build completed","body":"Release build succeeded","level":"success"}' \
  "$RUNBUOY_SERVER_URL/v1/hooks/$RUNBUOY_HOOK_ID/notifications"
```

Bearer 必须在 header，不得放 URL/query。

### 外部 Run

先 upsert：

```bash
curl --fail-with-body -X PUT \
  -H "Authorization: Bearer $RUNBUOY_HOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id":"machine_...",
    "title":"CI release",
    "source":"webhook",
    "execution_status":"CREATED",
    "live_activity_policy":"automatic"
  }' \
  "$RUNBUOY_SERVER_URL/v1/hooks/$RUNBUOY_HOOK_ID/runs/release-123"
```

Server 将 `hook_id + external_run_id` 映射成确定 UUID。body.machine_id 必须等于 Hook 所属 Machine。

再追加事件：

```bash
curl --fail-with-body -X POST \
  -H "Authorization: Bearer $RUNBUOY_HOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "type":"run.progress",
    "progress":{
      "kind":"determinate",
      "source":"explicit",
      "current":37,
      "total":100,
      "fraction":0.37
    },
    "phase":"building",
    "message":"37 targets complete"
  }' \
  "$RUNBUOY_SERVER_URL/v1/hooks/$RUNBUOY_HOOK_ID/runs/release-123/events"
```

Webhook endpoint 由 Server 取 `last_seq + 1`，可传 type、occurred_at、progress、phase、message、exit_code、
termination_reason、attention_status。状态转换和终态不可变规则与 Machine event 一致。

Webhook event 代码虽然接受 `Idempotency-Key` 并用它派生 event UUID，但重放时新计算的 seq 可能与第一次不同，
当前实现会触发 replay mismatch。集成方在该路径上不应依赖重复 POST 的完整幂等语义，直到实现修正并有测试覆盖。

## Live Activity 启动策略

### Automatic

收到 starting/started 时，为已订阅、允许 Live Activity 且有 push-to-start token 的 Device 创建
`LIVE_START` outbox，available_at 为 started_at + `LIVE_ACTIVITY_START_DELAY_SECONDS`（默认 5 秒）。

Run 在 start 发送前终态：pending start 取消。

- FAILED/LOST 且没有已发送 start：创建 error 普通通知。
- SUCCEEDED、真实 duration > 5 秒且没有已发送 start：创建 success 普通通知。
- SUCCEEDED ≤ 5 秒：不创建普通通知。

### Immediate

start delay 为 0。即使 Run 很短，只要 start 已发送且取得 update token，终态会走 LIVE_END。

### Disabled

不创建 LIVE_START。终态 fallback 规则仍执行：失败/丢失通知、超过 5 秒的成功通知。

`RunUpsert.notification_policy` 当前只保存到数据库，没有参与上述判断；不能作为已生效功能使用。

## Live Activity 容量、合并和优先级

### 容量

每 Device active/stale binding 默认最多 2 个。worker 处理新 LIVE_START 时若已满，将该 start 标记 suppressed，
不会结束或抢占已有 Activity。

### 合并

- 同一 Run + Device 的 pending update/end 使用共同 coalesce key，保留最新 full snapshot。
- start 使用独立 key。
- APNs `apns-collapse-id` 限 64 字符，允许离线设备只保留最新有用快照。

### 更新节流

- 普通 `run.progress`：默认不早于上次发送后 1 秒。
- Device 关闭 frequent updates：至少 15 秒。
- 连续 fraction 变化 <1%：把 available time 延到一个 update interval 后。
- 非 progress 事件（heartbeat、phase、message、attention、terminal）不使用这段 progress interval 逻辑。

### APNs priority

priority 10：start、end、Warning/Action Required、Failed/Lost、phase changed、第一条 progress、
或相对上次 progress 变化 ≥10%。其余通常 priority 5。

priority 决定 outbox 排序/APNs header，不改变执行状态。

## Live Activity payload

`aps` 使用 ActivityKit keys：

```text
timestamp
event = start | update | end
content-state
stale-date（start/update；end 无）
```

start 还含 attributes-type、input-push-token、attributes 和 alert。content-state 是完整当前 snapshot：
sequence、execution/health/attention、progress、phase、message、created/started/updated/ended、machine name、
显式 ETA、exit code。

### 有效期

- start：payload timestamp 后 5 分钟；
- update：到 stale-date，即最后 Machine update + 60 秒；
- end：timestamp 后 4 小时。

过期前未送达的 outbox 标为 expired。终态 payload 不设置 dismissal-date，使用 ActivityKit 默认 dismissal。

## APNs Provider

### Mock

`APNS_MODE=mock` 总是返回确定的 200 接受结果，并把 exact request payload/headers、queue/provider latency
写到 `push_attempts`。不需要 Apple credential，是 CI 唯一使用模式。

### Production

- HTTP/2、TLS；
- APNs Provider JWT 使用 ES256；
- JWT 每 50 分钟刷新，小于 Apple 一小时上限；
- development/production endpoint 按 `APNS_ENVIRONMENT`；
- 普通 topic 为 bundle ID，push type alert；
- Activity topic 为 `<bundle>.push-type.liveactivity`，push type liveactivity。

APNs 410 或 BadDeviceToken/ExpiredToken/Unregistered 等清空相应 token/binding。429、500、503 按指数退避，
最大 300 秒，最多 `OUTBOX_MAX_ATTEMPTS`（默认 6）；其他永久失败不重试。

## Activity reconciliation

iOS 同步当前 Activity 后：

- 新 activity 可替换 Server 的 `pending:<outbox id>` placeholder；
- update token generation 旧于现值时拒绝覆盖；
- binding active/stale 且 sequence 落后当前 Run，会排队发送最新 update；
- Run 已终态但 token 晚到，会排队 end；
- iOS 未再报告的真实 active binding 标记 ended；
- pending remote start 默认 300 秒未变成真实 Activity 时 cleanup 标记 expired。

## Retention

outbox worker 每轮执行上文列出的批量 retention cleanup。它会覆盖终态 Runs、events、notifications、
push attempts、terminal outbox、pairing sessions、audit metadata、safe log tails 和过期 pending Activity
placeholder；active Runs、active/stale Live Activities、pending outbox 以及精确位于 cutoff 的数据不会被误删。

## 自托管

### Mock 快速启动

```bash
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build
```

必须替换：PostgreSQL password、`CREDENTIAL_PEPPER`、Fernet `TOKEN_ENCRYPTION_KEY`。

### Production 关键环境

```dotenv
RUNBUOY_REGION=global
DATABASE_URL=postgresql+psycopg://...
CREDENTIAL_PEPPER=...
TOKEN_ENCRYPTION_KEY=...

APNS_MODE=production
APNS_ENVIRONMENT=production
APNS_BUNDLE_ID=your.bundle.id
APNS_KEY_ID=...
APNS_TEAM_ID=...
APNS_PRIVATE_KEY_PATH=/run/secrets/apns_key.p8

PAIRING_TTL_SECONDS=300
EVENT_RETENTION_HOURS=24
RUN_RETENTION_DAYS=30
NOTIFICATION_RETENTION_DAYS=30
PUSH_ATTEMPT_RETENTION_DAYS=7
OUTBOX_TERMINAL_RETENTION_DAYS=7
PAIRING_RETENTION_HOURS=24
AUDIT_RETENTION_DAYS=90
SAFE_LOG_TAIL_RETENTION_HOURS=24
RETENTION_CLEANUP_BATCH_SIZE=500
WORKSPACE_DELETION_CHALLENGE_TTL_SECONDS=300
LIVE_ACTIVITY_START_DELAY_SECONDS=5
LIVE_ACTIVITY_UPDATE_INTERVAL_SECONDS=1
LIVE_ACTIVITY_MAX_PER_DEVICE=2
LIVE_ACTIVITY_PENDING_TTL_SECONDS=300
OUTBOX_MAX_ATTEMPTS=6

MAX_REQUEST_BODY_BYTES=262144
RATE_LIMIT_IP_PEPPER=...
TRUSTED_PROXY_CIDRS=
RATE_LIMIT_FAIL_OPEN=false
RATE_LIMIT_DEVICE_BOOTSTRAP_PER_HOUR=20
RATE_LIMIT_PAIRING_CREATE_PER_HOUR=30
RATE_LIMIT_PAIRING_POLL_PER_MINUTE=120
RATE_LIMIT_RUN_UPSERT_PER_MINUTE=120
RATE_LIMIT_EVENT_BATCH_PER_MINUTE=240
RATE_LIMIT_NOTIFICATION_PER_MINUTE=60
RATE_LIMIT_WEBHOOK_EVENT_PER_MINUTE=240
MAX_MACHINES_PER_WORKSPACE=25
MAX_ACTIVE_RUNS_PER_MACHINE=100
MAX_PENDING_PAIRINGS_PER_IP=10
MAX_WEBHOOKS_PER_WORKSPACE=50
MAX_NOTIFICATIONS_PER_WORKSPACE_DAY=1000
MAX_EVENTS_PER_BATCH=100
```

生产部署要求：

- PostgreSQL 不直接暴露公网；
- 可信入口终止 HTTPS；
- APNs `.p8` 由 Secret Store 只读挂载；
- 数据库与 Token encryption key 一起备份；
- 监控 outbox backlog、永久 APNs 失败、API/DB 延迟，不记录 plaintext token；
- CLI 和自有 iOS 构建必须在配对前指向同一 Server/region；
- 永远不要添加 Machine inbox、控制队列、WebSocket、隧道或远程执行 endpoint。
