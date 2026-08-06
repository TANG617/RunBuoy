---
description: 在 macOS 或 Linux 上安装、验证、升级和卸载 RunBuoy CLI，并将可选 Python API 加入项目环境。
---

# 安装 CLI

RunBuoy CLI 发布在 [PyPI](https://pypi.org/project/runbuoy/)，支持 macOS 和 Linux，需要 Python 3.12 或更新版本。当前可用的是手动安装；一键安装器尚未发布。

## 系统依赖

持久 Run 需要系统提供的 `tmux`：

```bash
# macOS
brew install tmux

# Debian / Ubuntu
sudo apt update
sudo apt install tmux

# Fedora
sudo dnf install tmux

# Arch Linux
sudo pacman -S tmux
```

Python 包管理器不会安装这个系统依赖。

## 使用 uv（推荐）

macOS 可以直接运行 `brew install uv`。Linux 或没有 Homebrew 的环境可使用 uv 官方安装器：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool update-shell
```

重启终端，然后安装和验证 CLI：

```bash
uv tool install --python 3.12 runbuoy
runbuoy --version
runbuoy doctor
runbuoy capabilities --json
```

升级或卸载：

```bash
uv tool upgrade runbuoy
uv tool uninstall runbuoy
```

## 使用 pipx

无法采用 uv 时，可将 pipx 作为全局 CLI 备选：

```bash
pipx install runbuoy
pipx ensurepath
runbuoy --version
runbuoy doctor
```

升级或卸载：

```bash
pipx upgrade runbuoy
pipx uninstall runbuoy
```

## 指定版本

把 `X.Y.Z` 替换为需要的版本：

```bash
uv tool install --python 3.12 'runbuoy==X.Y.Z'
# 或
pipx install 'runbuoy==X.Y.Z'
```

## Shell 补全

显式选择当前使用的 Shell：

```bash
runbuoy completion install bash
runbuoy completion install zsh
runbuoy completion install fish
```

只需执行其中一个命令。重新打开终端后，命令、选项、合法枚举值和本地 Run ID 均可补全。

## 可选：项目 Python API

`uv tool install` 创建的是只供全局 CLI 使用的隔离环境，项目 Python 不会自动获得 import。进入包含 `pyproject.toml` 的项目根目录并单独声明依赖：

```bash
cd my-project
uv add --optional runbuoy runbuoy
uv sync --extra runbuoy
```

更新项目依赖：

```bash
uv lock --upgrade-package runbuoy
uv sync --extra runbuoy
```

从项目移除：

```bash
uv remove --optional runbuoy runbuoy
```

SDK 的 `progress()` 等调用必须发生在 RunBuoy 启动的目标进程树中。若不能修改项目依赖，可从目标进程使用 `runbuoy emit`；参见[进度模式](/guide/progress)。

## 故障排查

- 找不到 `runbuoy`：运行 `uv tool update-shell` 或 `pipx ensurepath`，然后重启终端。
- `doctor` 报告缺少 tmux：使用上面的系统包管理器命令安装，不要尝试用 pip 安装。
- `local_ready=true` 但 `delivery.ready=false`：本地执行仍已就绪；配对或 Server 可达性不可用，事件会保留在本地 outbox。
- 项目无法安装 API：确认项目 `requires-python` 包含 Python 3.12+，不要让安装器自动扩大项目支持范围。

卸载 distribution 不会自动删除本地配置、凭证、Run 历史或日志。如需清理历史，先使用受保护的 `runbuoy history prune` 命令，不要递归删除未知目录。
