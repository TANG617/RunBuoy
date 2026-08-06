# 官网内容、双语维护、构建与发布

RunBuoy 官网是位于 [`website`](../../website) 的 Rspress 2 静态站点，线上站点源地址配置为
`https://www.runbuoy.cloud`。它只负责产品介绍和文档，不承载 Server API，不读取用户的 Run，
也没有登录、配对或远程控制功能。

## 当前页面和用途

中文页面位于 `website/docs/zh`，英文镜像位于 `website/docs/en`：

| 路由 | 内容 |
| --- | --- |
| `/` | 产品首页：价值主张、Live Activity 视觉演示、三步上手、隐私和单向架构摘要 |
| `/docs/` | 使用文档入口 |
| `/guide/` | 快速开始和系统要求 |
| `/guide/install` | CLI 安装、升级、卸载、项目 Python API、tmux 和 Shell 补全 |
| `/guide/pairing` | 扫码、手工短码、暂停/恢复配对和连接检查 |
| `/guide/run` | 启动 Run、通知、本地管理、清理和日志尾部共享 |
| `/guide/progress` | structured、lines、regex、indeterminate 四种进度 |
| `/security` | 手机只读、凭证和本地进程隔离 |
| `/privacy` | 默认同步/不上传的数据、Token 和可选日志片段 |
| `/self-hosting` | Docker Compose、CLI 配置和生产注意事项 |
| `/download` | iOS App 获取状态；当前明确写为 App Store 尚未开放 |

语言切换由 `rspress.config.ts` 的 `zh`、`en` locales 提供。两种语言拥有对应 `_nav.json`
和 `guide/_meta.json`，分别控制顶部导航和指南侧栏排序。配置启用了 `languageParity`，因此新增或
删除公开页面时应同时维护两个语言目录，不能只更新一侧。

## 首页演示

首页 frontmatter 的 `hero`、`actions` 和 `features` 控制标题、按钮和卖点。主题覆盖组件
[`website/theme/components/HomeHero/index.tsx`](../../website/theme/components/HomeHero/index.tsx)
把 `hero.image` 渲染成纯前端绘制的 iPhone、灵动岛和 Live Activity 演示，而不是产品截图。

当前首页演示固定展示：

- `Gurobi experiment`；
- 72% 进度；
- “正在优化 / Optimizing”阶段；
- `Mac Studio`；
- 根据当前语言显示中文或英文文案。

这只是官网视觉样例，不与真实 Server 或 APNs 通信。修改示例数值或文案时，需要同时修改组件内的
中英文分支；修改首页标题、按钮和 feature 卡片则分别编辑 `zh/index.mdx` 与 `en/index.mdx`。

## 本地预览

要求 Node.js 和 npm。CI 当前使用 Node.js 22 和锁定的 `package-lock.json`。

```bash
cd website
npm ci
npm run dev
```

`npm run dev` 启动 Rspress 开发服务器并监听文件变化。最终提交前使用与 CI 相同的生产构建：

```bash
cd website
npm ci
npm run build
```

产物写入 `website/doc_build`。需要在本地检查生产产物时：

```bash
cd website
npm run preview
```

## 新增或修改页面

1. 在 `website/docs/zh` 和 `website/docs/en` 下创建相同相对路径的 `.md` 或 `.mdx` 文件。
2. 对用户可见内容做语义一致的双语维护，而不是只复制文件名。
3. 如果页面属于 Guide，更新两侧 `guide/_meta.json`；如果需要顶栏入口，更新两侧 `_nav.json`。
4. 页面之间使用站内绝对路由，例如 `/guide/run`，不要引用构建产物目录。
5. 图片放在 `website/docs/public`，页面以根路径引用，例如 `/brand/runbuoy-icon-light.png`。
6. 运行 `npm run build`，检查语言对等、MDX、内部路由和静态资源错误。

普通 Markdown 适合说明页；需要导入 Rspress 组件或编写 JSX 时使用 MDX。现有快速开始用
`Tabs`/`Tab` 展示不同平台和安装工具，首页用 HTML/JSX 组织三步流程。

维护 `/guide/install` 时以[安装、更新、项目接入与配对](../user-guide/installation.md)为事实来源。一键安装脚本尚未
发布时，官网只能展示手动安装命令；不得提前公开不可用的 `install.sh` URL。

## 发布

`.github/workflows/pages.yml` 在以下条件发布网站：

- `main` 分支中 `website/**` 或 Pages workflow 有变更；
- 手工触发 `workflow_dispatch`。

发布过程使用 Node.js 22、`npm ci`、`npm run build`，把 `website/doc_build` 上传为 GitHub Pages
artifact，再由 `actions/deploy-pages` 发布。配置的 `siteOrigin` 是 `https://www.runbuoy.cloud`，
Open Graph 图片为 `https://www.runbuoy.cloud/og.png`。

## 写官网文案时的代码事实边界

官网文案应先复用[产品功能总览](../features/README.md)，再按目标读者压缩。尤其不要超前承诺：

- iOS 26 以下支持；当前 Xcode 部署目标是 iOS 26.0；
- 中国大陆独立托管区域；当前 App 只开放 Global；
- 手机取消、重试、批准、输入或远程终端；产品是单向只读投影；
- 自动推测百分比或 ETA；RunBuoy 只展示真实上报的数据；
- 默认上传命令、参数、环境、源码或完整日志；
- App Store 已开放；当前 `/download` 明确标注“即将上线”；
- App 内可填写任意自托管地址；当前需要自有 iOS 构建配置；
- Rich Message 支持 Markdown、HTML 或可点击 `safe_link`；当前 App 按纯文本显示字段；
- Live Activity 满两条后会智能抢占；当前实现是抑制新的 start。

当代码行为和旧网页文字冲突时，以可执行代码、协议约束和测试为准，并同步更新中英文页面。

## 官网功能验收清单

- 中文和英文存在相同页面路径，导航均可达。
- 首页核心承诺没有越过单向只读边界。
- 示例命令与 [CLI 全命令与用法](../features/cli.md) 一致。
- 进度示例与 [进度和 SDK](../features/progress-sdk.md) 一致。
- 隐私、安全和自托管描述与 [Server 文档](../features/server.md) 一致。
- 下载状态、最低系统版本、托管区域等阶段性事实仍符合当前代码和发布状态。
- `npm run build` 成功，静态资源和站内路由无构建错误。
