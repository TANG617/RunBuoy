# 配对 iPhone

一台 iPhone 可以配对多台 Mac 或 Linux 电脑。

## 扫码配对

1. 在 iPhone 上打开 RunBuoy。
2. 进入“设置”，选择“配对新电脑”。
3. 在电脑上运行：

```bash
runbuoy pair
```

4. 扫描终端显示的二维码，并确认电脑身份。

二维码只包含短期配对挑战，不包含长期机器凭证。挑战五分钟后过期，并且只能交换一次。

## 无法扫码

在配对页面选择“使用配对码”，粘贴 `runbuoy pair` 输出的代码。

## 检查连接

```bash
runbuoy doctor
runbuoy capabilities --json
```

服务器不可达不会削弱安全边界，也不会让手机获得电脑控制权限。
