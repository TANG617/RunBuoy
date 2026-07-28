# 安装 CLI

RunBuoy CLI 发布在 [PyPI](https://pypi.org/project/runbuoy/)，支持 macOS 和 Linux，需要 Python 3.12 或更新版本。

## 使用 uv

```bash
uv tool install runbuoy
runbuoy doctor
```

如果终端还找不到 `runbuoy`：

```bash
uv tool update-shell
```

升级或卸载：

```bash
uv tool upgrade runbuoy
uv tool uninstall runbuoy
```

## 使用 pipx

```bash
pipx install runbuoy
runbuoy doctor
```

如果终端还找不到 `runbuoy`：

```bash
pipx ensurepath
```

升级或卸载：

```bash
pipx upgrade runbuoy
pipx uninstall runbuoy
```

## 指定版本

```bash
uv tool install 'runbuoy==0.1.2'
# 或
pipx install 'runbuoy==0.1.2'
```

## tmux

持久 Run 依赖系统提供的 `tmux`：

```bash
# macOS
brew install tmux

# Debian / Ubuntu
sudo apt install tmux
```

Python 包管理器不会安装这个系统依赖。
