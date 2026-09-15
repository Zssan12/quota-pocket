# v0.1.3 · 额度口袋 / Quota Pocket

[简体中文](#中文) · [English](#english)

<a id="中文"></a>

## 简体中文

首个公开测试版：在 Mac 采集 AI 账户余额和订阅额度，通过自己的 iCloud Drive，让 iPhone Scriptable 小组件展示。

### 本版包含

- CC Switch 独立查询、ChatGPT / Codex 订阅、Claude 订阅及 CodexBar 接入。
- 一行安装入口：检查 Python / Node.js、安装查询依赖、启动本地配置网页；另提供本地 Agent 安装提示词。
- 四步配置引导，手机端账户选择与排序。
- 1 / 2 / 4 格组件、分组轮换、订阅窗口重置时间。
- 白名单快照、离线缓存、失败状态与真实采集时间、同步诊断。
- 中英文 README 与安装提示词，MIT 许可。

### 已验证与限制

97 项 Python 测试、Scriptable 和配置引导测试通过；独立目录首次安装、重复打开和停止后重启通过，账户凭证与 iCloud 安装 ID 保持不变。真实 iPhone 曾确认端到端额度更新。

本版为 Pre-release。macOS 登录后台文件权限仍需实机验收，iCloud 传输和 iOS 桌面刷新不能保证固定周期。最新轮换逻辑已有模拟测试，仍需真机视觉确认。安装入口不会自动升级已有版本。页面和小组件目前使用中文，文档可切换中英文。

从 [README](README.md) 开始安装。反馈问题时请提供系统版本与脱敏的复现步骤，不要提交凭证或真实账户快照。

<a id="english"></a>

## English

The first public preview: collect AI account balances and subscription quotas on a Mac and display them in iPhone Scriptable widgets through your own iCloud Drive.

### Included

- CC Switch independent queries, ChatGPT / Codex subscriptions, Claude subscriptions, and CodexBar integration.
- A one-line installer that checks Python / Node.js, installs query dependencies, starts the local service, and opens setup; a prompt for local coding agents is also included.
- A four-step setup guide and on-device account selection and ordering.
- Widgets showing groups of 1, 2, or 4 accounts, group rotation, and subscription reset times.
- Allowlisted snapshots, offline caches, explicit failures, original collection timestamps, and sync diagnostics.
- Chinese and English READMEs and agent prompts, under the MIT License.

### Validation and limitations

97 Python tests plus Scriptable and setup tests passed. Fresh-directory installation, reopening, and restarting a stopped instance preserved account credentials and the iCloud installation ID. End-to-end quota delivery has been confirmed on a real iPhone.

This is a pre-release. macOS file permissions for login startup still need device validation. iCloud delivery and iOS Home Screen refresh do not have guaranteed intervals. The latest rotation logic has mock coverage but still needs visual confirmation on an iPhone. The installer does not upgrade existing installations. The UI and widgets are currently in Chinese; documentation is available in both languages.

Start with the [English README](README.en.md). Include OS versions and sanitized reproduction steps in bug reports; never attach credentials or real account snapshots.
