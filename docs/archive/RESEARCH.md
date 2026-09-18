# Claude / Codex 额度数据源调研

> 历史记录，内容对应当时版本，不作为当前安装或支持范围说明。请从[项目首页](../../README.md)开始。

查询日期：2026-09-13。依据公开 README、文档及关键代码；没有把社区私有接口说成稳定的公开 API。

## 首选：CodexBar

- 仓库：https://github.com/steipete/CodexBar
- Claude 数据源：https://github.com/steipete/CodexBar/blob/main/docs/claude.md
- Codex 数据源：https://github.com/steipete/CodexBar/blob/main/docs/codex.md
- CLI：https://github.com/steipete/CodexBar/blob/main/docs/cli.md
- HTTP 快照：https://github.com/steipete/CodexBar/blob/main/docs/dashboard-api.md
- 许可：MIT。当前主要发行平台为 macOS / Linux。

Claude 支持 OAuth、网页 Cookie、CLI PTY。OAuth 数据映射包括 five_hour、seven_day、部分模型专属周额度；缺少数值的组织套餐显示未知。登录权限和 Token 存储随 Claude Code 版本变化；不是有任意 API Key 就能读到。

本工具选择 OAuth CLI 固定命令和可选 HTTP schema-v1 快照，不自动启动 Claude PTY、读取浏览器 Cookie 或扫描会话。这样避开交互式信任提示、浏览器登录态和 PTY 副作用。需要这些恢复能力时由用户在 CodexBar 中处理。

## CC Switch

- 仓库：https://github.com/farion1231/cc-switch
- 查询文档：https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/2-providers/2.5-usage-query.md
- 进程内缓存：https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/services/usage_cache.rs
- 查询约定：https://github.com/farion1231/cc-switch/blob/main/src-tauri/src/usage_script.rs
- 许可：MIT。

已支持 Claude / Codex 原生订阅查询，第三方 Provider 可配置 JavaScript request/extractor。自动刷新主要针对当前 Provider。额度缓存是进程内结构，不持久化在 SQLite，因此“读取数据库”不等于“取出已有最新余额”。

第一版推荐独立查询，不修改 CC Switch。减少少量额度查询，不足以抵消维护修改版的升级冲突和安装成本。缓存导出仅保留为实验方案，补丁包含上游文件上下文，附 MIT 许可；尚未构建或实机验收。默认模式只读数据库并复用已启用脚本，JS 在 QuickJS WASM 内解释，网络由宿主做 GET、同源和 HTTPS 校验。

## Quotio / ZeroLimit

- Quotio：https://github.com/nguyenphutrong/quotio （MIT，macOS，提供 Standalone Quota Mode）
- ZeroLimit：https://github.com/0xtbug/zero-limit （MIT，Windows / macOS / Linux）

都值得参考多账户额度展示。它们与 CLIProxyAPI 的账户 / 代理生态关系更紧密。当前用户只需要读取额度，不需要额外引入代理，所以没有作为强制依赖。

## codex-usage-hud 的借鉴边界

- 仓库：https://github.com/fengbuming/codex-usage-hud
- 当前 README 的核心是读取本机 JSONL / SQLite 日志，显示 Token、缓存命中率、估算费用、自定义预算与任务等待状态，并注入 Codex 桌面界面。

值得借鉴一眼可见的紧凑展示和采集快照结构；它的日志费用与自定义预算不能替代平台订阅剩余额度。当前目标是手机 Widget，因此没有引入其桌面 renderer 注入、调试端口或会话日志扫描。

## 原生 Codex 的短路径

- 官方文档：https://learn.chatgpt.com/docs/app-server （由 developers.openai.com/codex/app-server 重定向）
- 接口：account/read、account/rateLimits/read。

平台返回 usedPercent、windowDurationMins、resetsAt、可选多额度桶。显示 `100 - usedPercent` 属于格式转换，不是本地计费估算。

## Claude 直接读取

参照 CodexBar 已公开的 OAuth 数据源说明，使用 GET `https://api.anthropic.com/api/oauth/usage` 与 `anthropic-beta: oauth-2025-04-20`。需要适当 OAuth 权限；兼容入口不发起 OAuth 登录、不刷新共享凭证。新增独立入口通过官方 CLI 登录到自己的目录；只刷新自身拥有的凭证，不把普通 API Key 当成订阅 Token。

接口可能变化或受账户权限限制。旧文件凭证不可用时，可使用独立连接或 CodexBar。独立连接的 macOS 专属钥匙串读取只发生在用户主动登录完成时；后台额度查询只读自己的文件。

## Widget 约束

- Apple：https://developer.apple.com/documentation/widgetkit/keeping-a-widget-up-to-date
- Scriptable：https://docs.scriptable.app/listwidget/
- Android：https://developer.android.com/develop/ui/views/appwidgets/advanced
- Tasker JavaScript：https://tasker.joaoapps.com/userguide/en/javascript.html

五分钟是采集周期和请求最早刷新时间，不是系统调度保证。浏览器手机效果仅作为示意。

## 依赖

`quickjs-emscripten` 0.31.0（MIT）以及锁文件中的其运行时依赖用于执行用户已有的 CC Switch 查询逻辑。QuickJS 本身为 MIT。其许可文件随 npm 包安装，不裁剪或改写。Web 界面没有外部 JS、字体、分析或广告依赖。


## 独立登录实现依据（2026-09-13）

- ChatGPT 使用本机 Codex `app-server generate-json-schema` 生成的 `LoginAccountParams`、`LoginAccountResponse`、`AccountLoginCompletedNotification` 和 `GetAccountParams` 核实协议。实际安装版本已验证初始化、空账户读取、浏览器授权发起和取消；没有替用户完成官方登录。参考入口：https://developers.openai.com/codex/app-server 、https://developers.openai.com/codex/auth 。本次文档抓取遇到 308 重定向循环，具体调用以本机生成协议和实测为准。
- Claude 的 CLI 参数来自本机 `claude auth login --help`，目录隔离参考 https://code.claude.com/docs/en/settings 的 `CLAUDE_CONFIG_DIR` 说明。专属钥匙串服务名与 `CLAUDE_SECURESTORAGE_CONFIG_DIR` 由当前安装 CLI 的实现核实，不扫描默认条目。
- 独立 Claude 刷新协议参考 CodexBar 的 `ClaudeOAuthCredentials.swift`（公开 OAuth client ID、`https://platform.claude.com/v1/oauth/token`、form-urlencoded refresh-token 请求），并与本机 CLI 常量交叉核对。没有复制整个 CodexBar 的凭证管理架构；旧工具凭证保持原归属。
- 当前仅验证了 Claude CLI 的独立未登录状态，完整授权、钥匙串权限及真实续期需要用户实际登录验证；协议模拟通过不代表真实账号已经接通。
