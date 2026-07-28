# 隐私说明

RunBuoy 按“默认不上传”设计，只同步在 iPhone 上展示运行状态所必需的有限数据。

## 默认同步的数据

- 机器标识与显示名称
- 安全标题
- 运行状态、阶段与结构化进度
- 安全消息、时间戳和退出码
- 通知与 Live Activity 所需的设备 Token

## 默认留在电脑的数据

- 完整命令与参数
- 当前工作目录和环境变量
- 源码、文件内容与用户输入
- stdout、stderr 与终端画面
- API Key、SSH Key 和云凭证
- 完整日志

## 可选日志片段

只有明确使用 `--share-log-tail 1..100` 时，RunBuoy 才会上传一个有界的日志末尾片段。上传前会去除 ANSI 控制字符、限制长度并脱敏；iOS 会明确标注该片段，服务端最多保留 24 小时。

## 凭证与设备 Token

长期凭证不会出现在 URL、二维码或普通日志中。服务端保存凭证哈希，并加密保存 APNs 与 Live Activity Token。

## 网站

本网站为静态站点，默认不加载广告或第三方分析脚本。GitHub Pages 可能按照其服务政策记录必要的访问与安全日志。

## 自托管

自托管部署由部署者决定服务器位置、保留策略与日志策略。部署者应保护 PostgreSQL、加密密钥、APNs 凭证与备份。

## 联系与更新

RunBuoy 是开源项目。隐私设计的权威实现和变更记录位于 [GitHub 仓库](https://github.com/TANG617/RunBuoy)。如有问题，可通过 [Issues](https://github.com/TANG617/RunBuoy/issues) 联系维护者。

最后更新：2026 年 7 月 28 日。
