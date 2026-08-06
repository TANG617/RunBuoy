# RunBuoy 安装、更新、项目接入与配对

本文给出 RunBuoy 的推荐安装实践、完整手动安装方法，以及未来一键安装器必须遵守的行为契约。
当前已经可以执行的是“手动安装”部分；仓库尚未提供公开的 `install.sh`，因此在安装脚本真正发布前，
不要把文中的规划 URL 作为可用命令放到官网首页。

## 推荐安装模型

RunBuoy 的同一个 PyPI distribution 同时提供：

- 全局 `runbuoy` CLI；
- Python API：`attention`、`message`、`phase`、`progress`。

最佳实践是在两个相互隔离的环境中各安装一次：

```text
uv tool 环境                  Python 项目环境
┌────────────────────┐       ┌────────────────────────┐
│ uv tool install    │       │ optional extra: runbuoy │
│ 全局 runbuoy 命令   │       │ from runbuoy import ... │
└────────────────────┘       └────────────────────────┘
```

对应命令：

```bash
uv tool install --python 3.12 runbuoy

cd my-project
uv add --optional runbuoy runbuoy
uv sync --extra runbuoy
```

`uv tool` 为命令创建隔离环境，不会让普通项目的 Python 自动获得 import。项目必须显式声明
`runbuoy` 依赖；重复安装到两个环境是正常设计，不是文件重复或配置错误。

Agent 在用户明确要求使用/安装 RunBuoy 时，可以执行上述 `uv tool` 和项目依赖命令。任何 sudo、系统包管理器
（brew/apt/dnf/pacman）或 curl installer 都必须先取得用户确认。Python 接入必须使用项目实际解释器检查
import；普通运行请求不得自动修改项目代码或依赖。

## 系统要求

- macOS 或 Linux；当前不支持 Windows。
- `tmux`，用于持久运行 Worker 和目标命令。
- RunBuoy iOS App，以及能连接对应 RunBuoy Server 的网络。
- CLI 和 Python API 当前要求 Python 3.12+。

使用 uv 时无需预先维护一个系统 Python 3.12；uv 可以下载并管理满足要求的 Python。`tmux` 是系统依赖，
不能由 wheel 安装，必须通过操作系统包管理器提供。

## 手动安装：macOS

### 1. 安装 tmux 和 uv

已有 Homebrew：

```bash
brew install tmux uv
```

也可以只用 Homebrew 安装 tmux，再使用 uv 官方安装器：

```bash
brew install tmux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

让 uv 的 tool bin 目录进入后续 Shell：

```bash
uv tool update-shell
```

重启终端。若希望在当前终端立即继续，可以临时执行：

```bash
export PATH="$(uv tool dir --bin):$PATH"
```

### 2. 安装全局 CLI

```bash
uv tool install --python 3.12 runbuoy
runbuoy --version
```

`--python 3.12` 固定 CLI tool 环境使用项目已测试的 Python minor；缺少时 uv 会自动安装。

### 3. 安装 Shell 补全

根据实际 Shell 明确选择一个：

```bash
runbuoy completion install zsh
# 或
runbuoy completion install bash
runbuoy completion install fish
```

重新打开终端后，命令、选项、枚举值和本地 Run ID 可以补全。

## 手动安装：Linux

### 1. 安装 tmux

Debian / Ubuntu：

```bash
sudo apt update
sudo apt install tmux
```

Fedora：

```bash
sudo dnf install tmux
```

Arch Linux：

```bash
sudo pacman -S tmux
```

### 2. 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool update-shell
```

重启终端，或在当前终端临时加入 tool bin：

```bash
export PATH="$(uv tool dir --bin):$PATH"
```

### 3. 安装 CLI 和补全

```bash
uv tool install --python 3.12 runbuoy
runbuoy --version

runbuoy completion install bash
# 使用 zsh/fish 时替换为对应名称
```

## 手动接入 Python 项目

进入包含 `pyproject.toml` 的项目根目录：

```bash
cd my-project
uv add --optional runbuoy runbuoy
uv sync --extra runbuoy
```

这会把 RunBuoy 放入 `[project.optional-dependencies].runbuoy` 并更新 `uv.lock`，不会增加默认业务依赖。
需要观测的环境明确启用 `--extra runbuoy`。requirements 项目应创建独立的
`requirements-runbuoy.txt`，不要修改默认 requirements 文件。

验证 import：

```bash
uv run --extra runbuoy python -c \
  "from runbuoy import attention, message, phase, progress; print('RunBuoy API ready')"
```

`import` 可以在普通 Python 进程中完成，但调用 `progress()` 等函数必须发生在 RunBuoy 启动的目标进程树中，
因为它们需要 Worker 注入的本地 Socket 和临时 Token。

推荐从项目环境启动结构化 Run，使 CLI 和 SDK 使用同一个锁定版本：

```bash
uv run --extra runbuoy runbuoy run \
  --progress structured \
  -- python experiment.py
```

也可以使用全局 CLI，让它启动项目环境中的目标程序：

```bash
runbuoy run \
  --progress structured \
  -- uv run --extra runbuoy python experiment.py
```

若项目的 `requires-python` 仍包含 Python 3.11 或更早版本，添加 RunBuoy optional extra 可能因依赖要求
不兼容而拒绝。
安装器不得擅自修改项目支持的 Python 范围；应让项目维护者明确决定是否升级到 Python 3.12+。

## 首次诊断和配对

安装完成后先检查本地依赖：

```bash
runbuoy doctor
runbuoy capabilities --json
```

`doctor --json` 使用 schema v2：`local_ready=true` 说明平台、Python、tmux 和本地存储满足执行条件；
`delivery.ready=true` 还要求已经配对且 Server 可达。交付不可用不会阻止本地 Run、日志、status、attach
或 cancel。

### 官方托管 Server

直接进入配对：

```bash
runbuoy device pair
```

终端会显示一次性 QR 和六位码。打开 iOS App，扫描或粘贴并确认电脑身份。配对挑战默认五分钟过期，
只能 claim/exchange 一次，不包含长期 Machine credential。

配对完成后验证：

```bash
runbuoy device status --check-server
runbuoy doctor --require-delivery
runbuoy demo notification
runbuoy demo live-activity
```

`demo` 会经过真实 Server/APNs 路径；普通安装脚本不应在未询问用户时自动发送测试通知。

### 暂停并恢复配对

需要先返回 Shell：

```bash
runbuoy device pair --no-wait
```

在 iPhone 确认后：

```bash
runbuoy device pair --resume
```

### 自托管 Server

Server URL 必须在配对前设置：

```bash
runbuoy config set --server-url https://runbuoy.example.com
runbuoy doctor
runbuoy device pair
```

配对后 region/server URL 被锁定。当前 iOS App 没有服务器地址输入 UI，自托管还需要让自有 iOS 构建的
`RUNBUOY_API_BASE_URL` 指向同一 HTTPS Server；当前端到端流程应使用 `global` region。

## 手动更新

### 更新全局 CLI

```bash
uv tool upgrade runbuoy
runbuoy --version
runbuoy doctor
```

`uv tool upgrade` 会保留首次安装时的版本约束。若之前安装了固定版本，现在明确希望切回最新稳定版：

```bash
uv tool install --python 3.12 'runbuoy@latest'
```

更新不会清除本地 Run、日志、配置或 Machine credential，也不应重新开始配对。

### 更新项目 API

在项目根目录只更新 RunBuoy，保留其他依赖的锁定版本：

```bash
uv lock --upgrade-package runbuoy
uv sync
```

然后验证：

```bash
uv run --extra runbuoy runbuoy --version
uv run --extra runbuoy python -c "from runbuoy import progress; print('RunBuoy API ready')"
```

全局 CLI 和项目依赖可以暂时处于不同版本。项目内执行 structured progress 时优先使用
`uv run --extra runbuoy runbuoy`，减少版本错位。当前产品尚未上线，CLI/SDK/JSON 契约直接采用当前最佳实践，不提供旧契约
兼容层。

### 更新 uv

只有通过 uv 官方 standalone installer 安装时才使用：

```bash
uv self update
```

若 uv 来自 Homebrew 或其他系统包管理器，应使用相同包管理器更新，例如：

```bash
brew upgrade uv
```

RunBuoy 安装器不应无条件执行 `uv self update`，否则可能越过原安装来源的管理边界。

## pipx / pip 手动备选

无法采用 uv 时，全局 CLI 可以使用 pipx：

```bash
pipx install runbuoy
pipx ensurepath
runbuoy --version
```

更新：

```bash
pipx upgrade runbuoy
```

requirements 项目在独立文件中声明可选观测依赖，例如 `requirements-runbuoy.txt`：

```text
runbuoy
```

然后只在需要观测的虚拟环境安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-runbuoy.txt

runbuoy --version
python -c "from runbuoy import progress; print('RunBuoy API ready')"
```

不要把 pipx 的内部虚拟环境加入项目 `PYTHONPATH`，也不要向 uv tool 环境手工注入项目依赖。

## 一键安装器规划

> 状态：尚未实现。以下是安装脚本发布前必须满足的接口和行为，不是当前可执行入口。

计划中的完整入口：

```bash
curl --proto '=https' --tlsv1.2 -LsSf \
  https://runbuoy.cloud/install.sh \
  -o /tmp/runbuoy-install.sh \
  && sh /tmp/runbuoy-install.sh --project .
```

不传 `--project` 时只配置全局 CLI；传入项目目录时，同时创建/更新名为 `runbuoy` 的 optional extra。

### 安装器必须幂等

首次运行：

1. 检测支持的平台、架构、Shell 和可用包管理器。
2. 在用户确认后安装缺少的 tmux。
3. 缺少 uv 时调用官方 HTTPS installer。
4. 用 uv-managed Python 3.12 安装最新稳定 RunBuoy tool。
5. 更新 PATH、安装明确识别出的 Shell completion。
6. 可选创建/更新项目的 `runbuoy` extra（或独立 requirements 文件）并验证 import。
7. 执行 doctor。
8. 未配对时进入 QR pairing。
9. 配对后执行严格诊断并输出下一步命令。

重复运行：

1. 只更新全局 tool 和指定项目中的 RunBuoy。
2. 不重复安装已有系统依赖。
3. 不重复写相同 Shell completion。
4. 已配对时只检查连接，绝不新建 pairing session。
5. 有 pending pairing 时恢复，而不是创建第二个 session。

### 建议参数

```text
--project PATH       同时添加或更新项目 Python API
--no-project         只安装全局 CLI
--no-pair            不进入配对，供 CI/无交互环境使用
--no-completion      不修改 Shell 配置
--python 3.12        指定 CLI tool runtime
--version VERSION    安装特定 RunBuoy 版本
--channel stable     stable/pre-release channel
--dry-run            显示动作，不修改系统或项目
--yes                接受受支持的系统依赖安装
```

### 需要先补齐的 CLI 能力

当前 `runbuoy device pair` 不会自动跳过已经配对的 Machine。实现安装器前，建议新增一个幂等入口：

```bash
runbuoy setup [--no-pair] [--timeout 300] [--json]
```

它应根据状态执行：

```text
paired          → 检查 Server，成功返回，不重新配对
pairing_pending → 恢复现有 session
unpaired        → 创建 session、显示 QR、等待确认
```

安装脚本随后只调用 `runbuoy setup`，不需要安装 `jq` 或用 Shell 正则解析 JSON。

### 安全要求

- 安装脚本源码必须与仓库版本一致并可直接审计。
- 只从 uv 官方 HTTPS URL 和 PyPI 安装，不使用未知镜像。
- 发布 installer 时同时提供版本化 URL 和 SHA-256 checksum。
- 发现 pipx/Homebrew 等其他来源已拥有 `runbuoy` executable 时停止并解释迁移，不自动 `--force` 覆盖。
- 需要 sudo 或修改 Shell 文件前说明具体动作；非交互模式缺少授权时失败，不尝试绕过。
- 不读取或打印 RunBuoy credential、Keyring、pairing exchange secret。
- 不自动创建 `pyproject.toml`，不修改项目 `requires-python`，不升级无关依赖。
- 不默认发送 demo 通知或 Live Activity。

### 支持承诺

安装器可以对明确支持的环境提供完整自动化，但不能承诺绕过：

- 没有 sudo/包管理器权限；
- 企业代理、私有 CA 或 PyPI 被阻断；
- 不受支持的 Linux 发行版；
- iPhone App 未安装、Server 不可达或用户未确认 QR；
- 项目声明的 Python 范围与 RunBuoy 不兼容。

遇到这些情况时必须保留已经成功的步骤，给出精确恢复命令，并保证重复执行不会破坏状态。

## 安装验收

全局环境：

```bash
command -v uv
command -v tmux
command -v runbuoy
runbuoy --version
runbuoy doctor --require-delivery
runbuoy capabilities --json
```

Python 项目：

```bash
uv run --extra runbuoy runbuoy --version
uv run --extra runbuoy python -c \
  "from runbuoy import attention, message, phase, progress; print('ok')"
```

配对后可由用户明确选择端到端验证：

```bash
runbuoy demo notification
runbuoy demo live-activity
```

## 卸载

删除全局 tool：

```bash
uv tool uninstall runbuoy
```

从项目依赖移除：

```bash
cd my-project
uv remove runbuoy
```

卸载 Python distribution 不会自动删除 RunBuoy 的本地配置、凭证、SQLite、Run manifest 或日志。先用
`runbuoy config path` 记录实际位置；如需清理历史，优先在卸载前使用受保护的 `runbuoy history prune`，
不要对未知目录执行递归删除。

## 相关文档

- [CLI 全命令与用法](../features/cli.md)
- [Python API 和四种进度](../features/progress-sdk.md)
- [iPhone 配对和 App 行为](../features/ios.md)
- [自托管 Server](../developer-guide/self-hosting.md)
- [Agent Skill 安装和执行规则](agent-skill.md)
