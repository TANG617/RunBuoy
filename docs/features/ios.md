# iOS App、通知与 Live Activity 功能参考

当前 App 是 SwiftUI + ActivityKit + WidgetKit 原生实现。本文按用户可见页面和系统行为说明实际能力。
源码位于 [`apps/ios/RunBuoyApp`](../../apps/ios/RunBuoyApp)、
[`RunBuoyWidgets`](../../apps/ios/RunBuoyWidgets) 和
[`RunBuoyShared`](../../apps/ios/RunBuoyShared)。

## 当前平台基线

- App、Widget、unit-test 和 UI-test target 的
  `IPHONEOS_DEPLOYMENT_TARGET = 18.0`；App 需要 iOS 18 或更高版本。
- iOS 26+ 使用 availability-guarded Liquid Glass button/container 和滚动边缘效果。
- iOS 18–25 使用标准 SwiftUI Material、bordered button、Tab 和 Navigation 组件；引导、通知权限、
  QR/手动配对、Runs、History、Machines、详情、离线缓存、设置、本机功能体验和 Live Activity 均保留。
- App 和 Widget 示例 bundle ID 分别为 `dev.runbuoy.app`、`dev.runbuoy.app.widgets`。
- App 支持竖屏和左右横屏。
- 支持英文与简体中文。
- Info.plist 启用 Push Notifications、后台 remote notification、Live Activities 和 Frequent Updates。

因此所有用户文案应写 **需要 iOS 18 或更高版本**。

## 第一次启动和引导

引导共四页：

1. 产品说明：电脑发送安全状态 → Server 中转 → iPhone 展示。
2. 数据区域：选择并永久锁定区域。
3. 通知说明：申请通知权限，创建匿名 Device/Workspace 身份。
4. 配对电脑：扫描一次性 QR、确认电脑显示名和平台。

### Device 引导

App 生成一个持久 installation ID，向 `/v1/devices/bootstrap` 发送 installation ID、App 版本和 OS 版本。
Server 返回 Device ID、Workspace ID 和 Device Bearer credential；credential 保存到 Keychain。

如果本地已有 Keychain identity，App 不重复 bootstrap。匿名 bootstrap 是 create-only：同一 installation ID
再次提交会返回 409，绝不会找回 Workspace、轮换 credential 或复活已重置的 Device。若 Keychain 已丢失，
App 丢弃旧 installation ID，生成新值并创建新的匿名 Workspace。

### 区域事实

代码模型保留 `global` 和 `cn`，但：

- `AppConfiguration.hostedRegions` 当前只有 `.global`。
- China 兼容值会被 `hostedRegion` 归一到 Global。
- bundled API 默认 `https://api.runbuoy.cloud`。
- App 没有让普通用户输入私有 Server 的 UI。

自托管 App 需要用构建设置 `RUNBUOY_API_BASE_URL` 编译自己的版本，或使用为旧部署保留的
`runbuoy.server-address` UserDefaults 注入。地址解析接受 HTTP/HTTPS、主机和可选端口，拒绝用户信息、
query、fragment 和非根路径。正常生产应使用 HTTPS。

## 配对方式

### 扫描 QR

- 使用相机仅识别 QR。
- 模拟器明确显示相机不可用；真机需要相机权限。
- 扫描后不会立即 claim，先显示电脑名/平台供确认。
- PairingCode 必须与 App 已选区域一致。

### 粘贴配对码

在“电脑”页可选择“使用配对码”，粘贴 CLI 输出的完整 `runbuoy://pair/...` 字符串或兼容 JSON payload。
代码也兼容 session 放在 query 的旧 URL。

### 深链配对

打开 `runbuoy://pair/<session>?challenge=...&machine=...` 会：

- 切换到设置 Tab；
- 打开配对确认页；
- 只解析和显示，不自动 claim。

### claim 后效果

iPhone 使用 Device credential 调用 pairing claim，Server 创建 Machine 和该 Device 的 subscription。
随后 CLI 才能交换到 Machine credential。App 刷新电脑/Run/消息列表。

一台 iPhone/Workspace 可配多台电脑；每台电脑只有 CLI 能修改 canonical display name。

## 主导航

App 有三个 Tab：

- **正在运行**：只显示 active Run。
- **历史**：显示终态 Run 和 Rich Message。
- **设置**：电脑、接收偏好、本机功能体验、缓存和链接。

“电脑”不是独立 Tab，从设置进入。

## 正在运行页

每条活动 Run 显示：

- 标题；
- 执行状态；
- 电脑本地图标和 Server display name；
- 阶段；
- 确定进度条、整数百分比、current/total/unit，或不确定进度动画；
- 非 Healthy 健康状态和非 None 关注状态；
- `startedAt → updatedAt` 的电脑确认执行时长；
- 最后 `updatedAt` 的相对心跳时间。

列表可下拉刷新，也有右上角刷新按钮。无活动 Run 时显示“All clear”；加载失败且无缓存时显示不可用状态。
点击进入详情。

## 历史页

历史页分为：

- Recent Runs：`SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST` 等非活动 Run。
- Recent Messages：CLI/API/Webhook 创建的通知记录。

两区各自默认显示前 5 条；超过 5 条时可“显示其余”或收起。Server 每次最多返回 200 Run 和 200 Message，
App 不做分页，因此“全部”是当前已加载集合，不代表无限历史。

### 按电脑过滤

顶部横向 Capsule 过滤栏含“全部”和各电脑。选项会合并：

- Server machines；
- Run 中的 machine ID/name；
- Message 中的 machine ID。

同一 ID 优先使用 Server Machine 名。过滤同时作用于 Run 和带 machine ID 的 Message；没有 machine ID 的
Message 只在“全部”中出现。

### Rich Message 展示

显示标题、可选 subtitle、body、级别图标、创建相对时间和结构化 fields。文本允许选择，fields 使用纯文本。

当前没有已实现的 Markdown/HTML/WebView 渲染；Server 的 `safe_link` 未进入 iOS `RichMessage` 模型，
所以不会显示或打开。

## Run 详情页

详情优先加载 `/v1/runs/<uuid>`；网络失败时若列表已有缓存快照，仍显示快照并在顶部提示错误。
若前台列表拿到 sequence 更大的 snapshot，会用新 snapshot 覆盖旧详情的投影部分，避免回退。

### 概览

- 标题和电脑名；
- execution、health badge；
- 非 None attention badge；
- 确定/不确定进度、phase、current/total/unit。

### 时间线

- Elapsed：活动 Run 每秒用 iPhone 当前时间临时刷新 `startedAt → now`；终态用 `startedAt → endedAt`。
- Explicit ETA：只有 snapshot 明确带 `estimated_end_at` 才显示。
- Started、Updated、Ended；
- Exit Code。

这里活动详情的 elapsed 是 UI 计时显示，与 Live Activity 的“仅电脑确认时长”不同；状态本身仍来自 Server。

### 安全消息

开启“显示安全消息”且 `safe_message` 非空时：

- 显示并允许文本选择；
- 提供“复制安全消息”。

### Run Feed

最多显示 Server 返回的前 500 个事件，按 sequence 升序：

- created、starting、started；
- progress、phase changed、message、attention required、heartbeat；
- succeeded、failed、cancelled、lost；
- 未识别类型用“Run updated”兼容显示。

每条可显示时间、阶段、消息和百分比。

### 安全日志片段

若 Run 含 `safe_log_tail`：

- 单独分区，以等宽字体逐行显示；
- 允许文本选择；
- 明示“这是电脑端明确共享的脱敏片段，完整日志留在电脑上”。

### 底部操作

只有两个本地分享动作：

- 复制 Run UUID；
- 调用系统 Share Sheet 分享标题、电脑名、原始状态值和可选 safe message。

没有取消、重试、批准、回复、attach、terminal 或打开电脑的按钮。

## 电脑列表和详情

### 列表

从设置 → 电脑进入，显示：

- Server display name；
- platform、CLI version；
- last seen；
- 当前 Device 是否仍有 subscription。

未订阅电脑显示 bell-slash/警告标记。右上角可以刷新、输入配对码或扫描新 QR。

### 详情

显示名称、平台、可选架构、CLI 版本、last seen、paired at。名称为只读，并提示从电脑 CLI 修改：

```bash
runbuoy config set --machine-name "Build Mac"
```

### 本地图标

每台电脑可在 iPhone 本地选择 Desktop、MacBook、Mac mini、Mac Studio、Mac Pro、Mac Pro Server 图标。
图标保存到 UserDefaults，不同步到 Server，也不修改电脑。

### 停止接收 / 移除配对

当前两个动作都可能调用 `DELETE /v1/machine-subscriptions/<id>`，只删除本 Device 的接收 subscription。

- 不撤销 Machine credential；
- 不删除 Machine；
- 不向 Machine 发送任何消息；
- 不删除 iPhone 的 Device Keychain identity；
- 不具备远程控制效果。

`removeLocalPairing` 这个内部函数名目前并未额外移除本地 credential。官网文案宜描述为“停止这台 iPhone
接收该电脑更新”，不要承诺完整的账号/身份清除。

## 设置页

### Connections

- 电脑数量和入口；
- 已选数据区域；
- 当前 Server 主机/端口；
- 区域不可更改提示。

### Product

进入本机“功能体验”。

### Notifications and Display

#### Notifications

本地开关会把 Server 的 `failure_notifications_enabled` 和 `success_notifications_enabled` 同时设为同一值。
它不撤销 iOS 系统通知授权，也不取消 APNs registration。系统层通知需到 iOS 设置管理。

#### Live Activities

写 Server 的 `live_activities_enabled`。若系统 `ActivityAuthorizationInfo.areActivitiesEnabled=false`，
开关禁用并给出提示。

#### Show safe messages

保存为 iPhone 本地 `@AppStorage`，Server patch 不包含这一字段。当前它会：

- 隐藏详情的 safe message 独立分区；
- 隐藏历史页全部 Rich Message 分区。

但当前实现仍可能在 Run Feed 事件中显示 event message，分享摘要也会加入 Run 的 safe message。
因此它不是“彻底隐藏所有安全消息”的隐私总开关。

### Storage

“清除本地缓存”删除 App Support 中带文件保护的 `read-cache.json`，并清空当前内存列表。
它不解除配对、不删除 Keychain、不删 Server 数据；下一次前台自动刷新会重新下载有权读取的数据。

### About

链接到官网、隐私页和自托管页。

## 本机功能体验

设置 → 功能体验无需配对：

- 检查 Live Activity 系统开关和通知权限；
- 能跳转 iOS 系统设置；
- 创建一个不使用 push token 的本机 ActivityKit Activity；
- 状态可按顺序或菜单切换：Starting → Indeterminate → 72% Progress → Warning → Stale → Succeeded；
- 菜单也能直接选择 Failed；
- 终态在约 60 秒后按 demo dismissal policy 清除；
- 可立即停止并清除所有 demo activities；
- 可创建 5 秒后触发的本地通知。

Demo 属性包含独立 marker，`ActivityTokenCoordinator.shouldSynchronize` 会排除它，因此不注册到 Server，
也不创建 Run。页面底部只是解释真实链路。

## 刷新、缓存和离线

### 自动刷新

完成引导、App 在前台且不是 UI Preview 时，每 3 秒：

1. 并行 GET runs、machines、notifications；
2. 更新内存模型；
3. 原子写缓存；
4. 用最新 Run sequence 本地协调已有 Live Activity。

多个同时 refresh 会合并到同一个 Task。

### 其他刷新触发

- App 切回 active；
- 下拉刷新；
- 页面刷新按钮；
- 前台收到通知；
- 用户点通知；
- 启动完成。

### 离线缓存

缓存包含 runs、machines、messages 和保存时间，写入使用
`completeFileProtectionUnlessOpen`。冷启动会先恢复缓存并标为 Offline；请求失败但已有内容时保留内容并显示横幅。
无任何缓存且失败时显示不可用页面。

## 通知行为

- 引导请求 alert、badge、sound 权限。
- APNs device token 转成 hex 后注册到 Server；普通日志不输出 token。
- App 在前台收到通知时显示 banner + sound，并刷新内容。
- 用户点击通知后刷新；本机 demo 通知还会打开 `runbuoy://demo/notification`。
- Server 的普通 APNs payload包含 alert title/body/subtitle，以及 RunBuoy notification ID、level、可选 Run ID。
- iOS App 的历史消息来自 Read API，不是从 APNs payload反推。

## Live Activity Token 生命周期

`ActivityTokenCoordinator` 在引导完成后：

- 监听 `pushToStartTokenUpdates`；
- 监听 Activity 创建；
- 监听每个真实 Activity 的 `pushTokenUpdates`；
- 监听 frequent push 设置变化；
- App 回前台时重扫当前 Activities。

Token 带本地单调 generation；相同 generation 的旧注册由 Server 拒绝。注册和 activity sync 最多重试 6 次，
从 0.5 秒指数退避到 8 秒。Demo Activity 不参与。

同步给 Server 的内容包括 activity ID、Run ID、可选 update token、generation、active/stale/ended/dismissed
状态和最后 sequence，以及系统 frequent pushes 开关。

## 前台 Live Activity 修复

成功刷新 Run 后，App 对当前真实 Activity：

- active Run 且 Server sequence 更大：本地 `activity.update`；
- terminal Run 且 sequence 不旧：本地 `activity.end(..., .default)`；
- 旧 sequence 不覆盖新 Activity 状态。

这样即使某次 APNs update/end 丢失，用户打开 App 后仍可修复显示。

## 锁定屏幕和灵动岛

### 展示内容

- Lock Screen：标题、确定/不确定进度、状态图标、电脑名和时间。
- Dynamic Island expanded：标题、进度、footer。
- compact leading/minimal：状态图标。
- compact trailing：终态时间、百分比，或电脑确认耗时。

### 状态优先级

显示样式按以下逻辑：

1. terminal execution：Succeeded / Failed / Cancelled / Lost；
2. stale/offline；
3. ACTION_REQUIRED；
4. WARNING；
5. Starting 或 Running。

因此终态样式会覆盖 attention/stale 的颜色和图标。

### 时间语义

活动状态使用 `createdAt`、`startedAt`、`updatedAt`、可选 `endedAt`：

- 活动 Run：显示 `createdAt（旧载荷回退 startedAt）→ updatedAt`，不会跟 iPhone 本地秒表自行前进；
- 没新电脑确认时数字冻结；60 秒后 ActivityKit 标为 stale；
- 终态：以 `endedAt` 为锚点，缺失时回退 `updatedAt`；
- 结束后不足 1 分钟显示“刚刚”，之后显示已完成分钟数，不显示秒；
- Widget 为最多约 4 小时的可能可见期准备逐分钟 Timeline 刷新。

### 深链

- 普通 Activity：`runbuoy://runs/<Run UUID>`，打开正在运行 Tab 的详情。
- Demo Activity：`runbuoy://demo/live-activity`，打开设置里的功能体验。

Widget 没有按钮、App Intent、取消或批准操作。

## 可访问性与本地化

代码显式处理：

- Dynamic Type，包括辅助功能字号时切为纵向布局；
- Reduce Motion：关闭/简化进度动画和展开动画；
- Reduce Transparency：使用实色背景；
- Increased Contrast：增加描边和对比；
- VoiceOver label/value；
- 英文和简体中文；
- 亮色、暗色预览。

UI 测试覆盖引导、主页面、深链、过滤、偏好持久化、配对、缓存反馈、功能体验和核心屏幕 Accessibility Audit。

## 必须用真机验证的能力

模拟器/普通构建不能证明：

- 相机扫码；
- APNs device token 和真实投递；
- push-to-start token 生成/轮换；
- Activity update token 和远程 update/end；
- 真正的锁定屏幕/灵动岛表现；
- 生产签名、entitlements 和 App Store 接受。

这些路径虽有注入、Mock、fixture 和单测，发布前仍需 iOS 18 或更高版本真机、Apple Developer 配置和
生产 Server 验证。
