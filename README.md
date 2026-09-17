# 额度口袋 · Quota Pocket

**把中转 API 余额、ChatGPT / Claude 订阅额度放到 iPhone 桌面。**

简体中文 · [English](README.en.md)

```text
Mac / Windows 采集 → 你的 iCloud Drive → iPhone Scriptable 小组件
```

密钥和登录凭证留在电脑。无需服务器、域名或 VPN 配对，不读取对话、不发起模型请求。

## 能看什么

- **中转余额**：读取 CC Switch 已配置的额度查询脚本，保留原币种。
- **订阅额度**：支持多个 ChatGPT / Claude 账户，展示剩余比例与重置时间。
- **手机组件**：小、中、大尺寸，账户选择、排序、分组轮换，颜色随余量变化。
- **真实状态**：离线保留上次结果和采集时间，未知额度不会显示为零。

## 开始使用

准备 [Python 3.9+](https://www.python.org/downloads/)、[Node.js 20+](https://nodejs.org/)，以及 iPhone 上的 [Scriptable](https://scriptable.app/)。电脑和手机需登录同一 Apple 账户并开启 iCloud Drive；Windows 还需安装 iCloud for Windows。

### Mac

首次安装最新版源码：

```sh
git clone https://github.com/Zssan12/quota-pocket.git
cd quota-pocket
bash install.sh --source "$PWD"
```

自动打开本地配置页。安装后可关闭终端；重启电脑后双击安装目录 `~/Library/Application Support/QuotaPocket` 中的 `Start Quota Pocket.command`。

已有安装不会被此命令自动升级，详见 [Mac 后台与升级](MAC.md)。

### Windows（预览版）

```powershell
git clone https://github.com/Zssan12/quota-pocket.git
cd quota-pocket
npm ci --ignore-scripts
.\start-windows.cmd
```

采集时保持启动窗口打开。更新、iCloud 路径和代理问题见 [Windows 指南](WINDOWS.md)。

没有 Git？[下载 ZIP](https://github.com/Zssan12/quota-pocket/archive/refs/heads/main.zip) 并解压，在项目目录执行对应安装命令。也可以[让本地 AI 助手帮你安装](AGENT-INSTALL.md)。

## 连接手机

1. 在电脑配置页连接账户，确认余额或订阅额度查询成功。订阅授权需相应的 Codex / Claude CLI。
2. iPhone 打开一次 Scriptable，允许使用 iCloud。
3. 电脑进入“手机小组件”，启用 iCloud，记下生成的脚本名称。
4. 手机运行该脚本、选择账户，再添加 Scriptable 桌面组件并选中它。

## 使用前知道这些

- 电脑睡眠或关机后不产生新数据。默认每 5 分钟采集，**不保证手机桌面每 5 分钟更新**。
- iCloud 同步和 iOS 重绘由系统调度。点开脚本可重新读取，不能强制云端立即送达；轮换也依赖系统运行脚本。
- Windows 已有基础文件链路和中转余额采集实测；订阅授权、后台自启动及最新版本完整手机链路仍待验收。
- Clash/Mihomo 用户遇到 Fake-IP 提示时，在 CC Switch 独立查询设置中开启“代理 Fake-IP 兼容”；默认关闭。

## 更多

[Mac 运维](MAC.md) · [Windows 指南](WINDOWS.md) · [同步排查](CONNECTIVITY.md) · [验证记录](VALIDATION.md)

贡献前运行 `npm ci --ignore-scripts` 和 `npm test`。反馈请附系统版本、步骤和脱敏错误，不要上传 `.state`、密钥或账户快照。

[MIT](LICENSE) · 感谢 [Scriptable](https://scriptable.app/)、[CC Switch](https://github.com/farion1231/cc-switch) 和 [CodexBar](https://github.com/steipete/CodexBar)。本项目与相关服务商无官方关联。
