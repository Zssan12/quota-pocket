# v0.2.0 · 多订阅账号 / Multiple subscription accounts

## 简体中文

- Codex、Claude 均支持添加多个独立订阅账号，可分别备注、停用 / 启用和重新授权。
- 原有账号凭证与额度 ID 保留，无需重新登录，手机选择继续有效。
- 每个账号独立查询和失败退避；重新授权不会覆盖其他账号，停用不删除凭证。
- 新增 13 项回归测试，覆盖旧状态兼容、账号隔离、查询失败、授权失败和管理权限。网页已用模拟账号验证新增、备注、停用、启用和重新授权，320 / 390 / 1440 像素宽无横向溢出。

本版仍为测试版。多个真实账号的授权需用户在官方页面逐个完成；模拟测试不能代替所有账户和上游版本的实测。登录后台权限、iCloud 到达时间与 iOS 刷新限制仍然存在。安装器不会自动升级已有安装；重跑命令会打开已有版本。

## English

- Add multiple independent Codex and Claude subscription accounts, each with its own label, enable/disable controls, and reauthorization.
- Existing credentials and quota IDs are preserved, so previous logins and phone selections continue to work.
- Queries and retry backoff are independent per account. Reauthorization does not replace other accounts; disabling does not delete credentials.
- Added 13 regression tests for existing-state compatibility, account isolation, query and login failures, and management authorization. Browser checks with synthetic accounts cover adding, renaming, disabling, enabling, and reauthorization, with no horizontal overflow at 320 / 390 / 1440 pixels.

This remains a preview. Users must authorize their real accounts on the official pages; mocks do not establish compatibility with every account or upstream version. Background permissions, iCloud delivery, and iOS refresh limitations still apply. The installer does not upgrade existing installations; rerunning it opens the installed version.

---

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
