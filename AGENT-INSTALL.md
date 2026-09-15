# 让本地 Agent 帮你安装

**简体中文** · [English](AGENT-INSTALL.en.md)

把下面整段复制给能操作这台 Mac 的 Codex、Claude Code、WorkBuddy 等本地 Agent。普通网页聊天若无法访问本机，不能代替你执行安装。默认从本项目 GitHub 仓库安装；如果已经下载源码，也可把提示词中的项目位置换成本地文件夹路径。

```text
请帮我在这台 Mac 安装并启动开源项目 Quota Pocket，直到自动打开配置网页。

项目位置：https://github.com/Zssan12/quota-pocket
版本：v0.2.0 测试版。若该标签不存在，请说明并让我选择可用版本，不要猜仓库地址。

这个项目在 Mac 采集 AI 账户额度，经字段白名单过滤后写入我自己的 iCloud Drive，由 iPhone Scriptable 展示。凭证只保留在 Mac。

请按以下流程实际执行，不要只给我操作说明：
1. 先阅读项目 README.md 和 install.sh / install.py，遵守项目及当前会话的操作约束。
2. 确认系统是 macOS，检查 Python 3.9+、Node.js 20+ 和 npm。已有工具可用就复用。若缺少工具且已装 Homebrew，可安装缺少的工具；没有 Homebrew 时给我官方安装入口，并指出需要我完成哪一步。不要使用 sudo，不修改系统自带 Python。
3. 如果是 GitHub 地址，将指定版本下载到独立目录；如果是本地路径，直接使用它。不要在别的项目根目录初始化或修改 Git。不要删除或覆盖我已有的源码与账户状态。
4. 在源码目录执行 bash install.sh --source "$PWD"。它会安装到 ~/Library/Application Support/QuotaPocket，保留已有安装的账户和安装 ID。不要为了重新安装而删除 .state；这个入口不会自动升级已有安装。
5. 验证本机服务已启动，配置网页已打开。遇到端口占用先确认进程身份，不要强杀进程。不要把 API Key、Token、带凭证的网页地址或真实账户信息贴到对话和日志里。
6. 到网页需要连接 ChatGPT、Claude 或填写 API Key 时停下来，让我在本机网页完成登录。先询问我需要哪种来源，不要自行启用所有来源，不读取对话内容。需要 Codex CLI 或 Claude CLI 时，再按项目说明检查对应工具。
7. 继续带我完成：确认额度采集成功 → 开启 iCloud → 在 iPhone Scriptable 运行专属脚本 → 添加桌面组件。Mac 和 iPhone 要使用同一个 Apple 账户并开启 iCloud Drive。手机操作由我完成；不要把 Mac 写入成功当作手机已经收到。
8. 默认先使用安装器启动的进程。登录自动启动是实验功能，只有我需要时再配置，并检查 macOS 文件访问权限。不要开启公网入口或部署同步服务器。

完成后简短告诉我：安装位置、是否启动成功、以后怎么打开、下一步需要我在网页或手机做什么。不要删除文件或目录来清理安装。
```

你不需要把账户密钥或登录凭证填进提示词。账号授权在项目的本地管理网页中完成。
