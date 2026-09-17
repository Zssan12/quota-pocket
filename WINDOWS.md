# Windows 使用指南

## 首次启动

准备 Python 3.9+、Node.js 20+、iCloud for Windows；电脑和 iPhone 使用同一 Apple 账户并开启 iCloud Drive。手机先打开一次 Scriptable 并允许 iCloud。

```powershell
git clone https://github.com/Zssan12/quota-pocket.git
cd quota-pocket
npm ci --ignore-scripts
.\start-windows.cmd
```

在打开的配置页连接数据源 → 确认额度 → 启用 iCloud。手机运行页面显示的脚本，再添加 Scriptable 小组件。

中转余额需本机 CC Switch 已配置查询脚本。首次建议只接一个账户，确认电脑和手机的余额、币种、采集时间一致。

## 日常使用与更新

双击 `start-windows.cmd`。采集时保留窗口，Ctrl+C 停止；Windows 重启后需再次启动，暂不提供开机自启动。

更新前先停止采集，在原项目目录运行：

```powershell
git pull --ff-only
npm ci --ignore-scripts
.\start-windows.cmd
```

如果 Git 提示本地改动冲突，先保留改动再处理，不要覆盖 `.state`。从 Mac 转移源码时也不要复制 Mac 的 `.state` 或 `node_modules`。

## 找不到 iCloud 文件夹

默认路径：

```text
%USERPROFILE%\iCloudDrive\iCloud~dk~simonbs~Scriptable
```

等待 iCloud 初始化结束。如果使用自定义位置，在项目目录创建 UTF-8 文件 `windows-icloud-path.txt`，只写 **Scriptable 容器完整路径**，不加引号，例如：

```text
D:\iCloudDrive\iCloud~dk~simonbs~Scriptable
```

重启采集器后生效。不要填写普通 iCloud 根目录，也不要自行加上 Mac 的 `Documents`。更换位置不会删除旧文件。

## Clash / Mihomo Fake-IP 兼容

看到“Provider 域名解析到代理 Fake-IP”时，在 **连接数据源 → CC Switch 独立查询** 勾选 **代理 Fake-IP 兼容**，保存后刷新。

默认关闭。只放行域名解析得到的 `198.18.0.0/15`；HTTPS、同源和其他内网限制不变。设置重启后保留，关闭后恢复拒绝；之前的余额可能仍以旧数据显示。

旧配置未保存开关时兼容 `QUOTA_POCKET_FAKE_IP=1`。保存后的开关优先于环境变量，且只影响 CC Switch 独立查询。

## 手机没更新

先确认电脑采集时间变新，再在 Scriptable 手动运行对应脚本。第二轮应读到新的采集时间，余额不一定变化。手动运行已更新而桌面未变，通常是 iOS 尚未重新绘制。

Windows 基础文件同步（含手机蜂窝网络）和真实中转余额查询已有实测；CI 覆盖 Windows 启动与文件测试。订阅登录、重启恢复及最新版本完整手机链路仍需验收。文件送达不代表桌面准时刷新。
