<div align="center">

# 额度口袋 · Quota Pocket

**在 iPhone 桌面查看 AI 账户额度，密钥留在 Mac。**

**简体中文** · [English](README.en.md)

macOS · iCloud Drive · iPhone Scriptable · MIT

</div>

Quota Pocket 是一个开源的 AI 额度查看工具：Mac 负责读取中转 API 余额和订阅额度，通过你自己的 iCloud Drive，同步到 iPhone 的 Scriptable 小组件。无需部署服务器，也无需让手机连接 Mac 的网络地址。

## 可以做什么

- **集中查看额度**：接入 CC Switch 查询、ChatGPT / Codex 订阅、Claude 订阅及 CodexBar。
- **手机桌面展示**：小、中、大组件每组显示 1、2、4 个账户；选择超出容量时按组轮换，订阅显示各窗口的重置时间。
- **按步骤配置**：安装后自动打开本地网页，跟随账户连接、额度确认、iCloud 同步和手机配置四步完成。
- **保留真实状态**：失败或离线时显示上次成功数据与原时间，不把未知额度当成零，也不把重置时间已到当成额度已恢复。

```text
Mac 采集 → 白名单额度快照 → 你自己的 iCloud Drive → iPhone Scriptable
```

API Key、OAuth Token 和登录凭证仅保存在 Mac。iCloud 中的额度快照只包含白名单允许的展示字段；iPhone 不需要账户密钥。项目只查询额度，不读取对话、不估算消费、不发起模型请求。

> v0.1.3 测试版：核心采集与 iCloud 链路已验证；后台权限和不同 iPhone 系统状态仍需实机验收。配置网页与小组件目前使用中文，上方链接切换文档语言。

## 安装

需要 macOS、Python 3.9+、Node.js 20+（含 npm）。Mac 和 iPhone 使用同一 Apple 账户，并开启 iCloud Drive。

<a id="agent-install"></a>

**不想操作终端？** 把下面整段提示词复制给能操作这台 Mac 的 Codex、Claude Code、WorkBuddy 等本地 Agent，让它帮你检查环境、安装项目并打开配置网页；账户登录和手机操作由你完成。

<details open>
<summary>安装提示词（可直接复制，也可点击收起）</summary>

```text
请帮我在这台 Mac 安装并启动开源项目 Quota Pocket，直到自动打开配置网页。

项目位置：https://github.com/Zssan12/quota-pocket
版本：v0.1.3 测试版。若该标签不存在，请说明并让我选择可用版本，不要猜仓库地址。

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

</details>

不要把密钥或登录凭证填进提示词；账户授权在本地配置网页中完成。

### 一行安装并打开配置网页

在 Mac 终端粘贴运行：

```sh
curl -fsSL https://raw.githubusercontent.com/Zssan12/quota-pocket/v0.1.3/install.sh | bash -s -- --repo Zssan12/quota-pocket
```

安装器检查环境、下载指定版本、安装查询依赖、启动本机服务并自动打开配置网页。源码来自对应 GitHub 仓库，npm 依赖按锁文件安装且禁用安装脚本。不会替你安装系统工具或启用登录自动启动，也不需要 sudo。

缺少 Python 或 Node.js 时会提示。已有 Homebrew 可运行 `brew install python node`；也可从 [Python 官网](https://www.python.org/downloads/macos/)和 [Node.js 官网](https://nodejs.org/en/download)安装。完成后重新打开终端，再执行安装命令。

### 已下载源码

从 Code → Download ZIP 下载并解压，或克隆仓库。在终端进入包含 `install.sh` 的项目目录，执行：

```sh
bash install.sh --source "$PWD"
```

两种方式都安装到 `~/Library/Application Support/QuotaPocket`。重复运行会打开已有安装，保留账户和安装 ID，**不会自动升级**。安装成功后可以关闭终端；Mac 重启后再次执行安装命令，或双击安装目录中的 `Start Quota Pocket.command`。首次安装的下载和依赖准备文件保留在 `.installer`，不要把这个目录当作公开源码上传。

### 按网页引导连接手机

1. iPhone 安装并首次打开 Scriptable，允许使用 iCloud。
2. 在 Mac 管理页点“一步步配置”，按“连接账户 → 确认额度 → 同步到 iCloud → 添加手机组件”完成。已有步骤自动识别，高级选项默认收起。
3. “手机小组件”中启用 iCloud，同步成功后显示专属脚本名称。
4. 等待脚本出现在 iPhone Scriptable，运行一次。长按桌面添加 Scriptable 小组件，编辑并选择该脚本。
5. 确认手机收到额度。登录后自动启动是可选步骤，见下文。

本地管理服务只监听 `127.0.0.1:8931`。安装入口自动打开带本机管理权限的页面；已有服务运行时复用它，不会重复启动采集。直接输入网址而未带管理凭证时，账户数与周期显示未知。

## 后台与升级

登录自动启动目前为实验功能。macOS 可能拒绝后台 Python 访问 iCloud 或数据源文件；尚未完成授权后的登录启动验收。建议先用安装器完成配置。若登录后台报权限错误，在安装目录执行 `python3 service_manager.py disable`，再重新运行安装命令恢复采集。服务已启动不等于同步成功。

以下命令在安装目录中执行：

```sh
python3 service_manager.py start
python3 service_manager.py status
python3 service_manager.py restart
python3 service_manager.py disable
```

start / restart 启用登录启动并通过 launchd 运行当前版本；disable（stop 同义）停止采集并禁用下次登录启动。账户、配置、日志及 iCloud 文件保留。停用后，运行 `python3 server.py --open` 可手动打开管理端。

管理页显示运行版本与已安装副本的构建标识。管理页按钮只重启已安装副本。安装命令当前只支持首次安装和重新打开；自助升级入口尚未提供。开发者从同一个源码目录通过服务管理器安装的实例，可在该源码目录运行 `python3 service_manager.py restart` 更新；这会启用登录启动，需要验证文件权限。

同一状态目录有进程锁，避免重复采集和写入。启用登录后台后，进程退出由 launchd 恢复；安装器直接启动的进程退出后需要重新打开。Mac 睡眠时不采集，唤醒后择机补查。默认 5 分钟周期，保留用户已有自定义值；失败退避且保留上次成功数据。

运行副本和账户状态位于 `~/Library/Application Support/QuotaPocket`。开发源码与原状态文件保留。首次迁移保持安装 ID 与账户，后续只更新代码，不覆盖运行账户状态。自定义端口和状态目录由终端管理。launchd 不加载 shell 配置；必须让 Node、Codex、Claude 可执行程序在安装时 PATH 中，供应商凭证应通过独立登录保存，不依赖临时 shell 环境。

后台在 Application Support 中运行；访问 iCloud 仍可能需要 macOS 文件授权。后台日志位于 `~/Library/Logs/QuotaPocket/collector-error.log`。不要用 sudo 启动本工具。后台操作错误在运行目录的 `.state/service-action.log`；采集日志超过 2 MiB 时保留近期约 1 MiB，不删除文件。

## 数据源

| 来源 | 内容 | 接入 |
| --- | --- | --- |
| CC Switch 独立查询 | 已启用查询脚本的余额、套餐额度 | 检测本机数据库，安装 Node 依赖并启用 |
| ChatGPT 订阅 | Codex 的额度窗口与重置时间 | 管理页独立授权，需 Codex CLI |
| Claude 订阅 | 五小时、每周及模型额度 | 管理页独立授权，需 Claude CLI；普通 API Key 不适用 |
| CodexBar | 工具返回的额度 | 安装并配置其 CLI 后启用 |

连接订阅使用隔离登录目录，不更改原工具账户。独立 CC Switch 查询会额外请求供应商，与原工具同时自动查额度会重复查询。缓存读取是实验兼容模式，需要原工具导出补丁。

部分中转站不支持当前只读查询约束：仅 HTTPS、同源 GET、拒绝重定向。未知额度显示未知，余额保留原币种，不将不同币种相加。

如本人明确使用 Fake-IP 代理，可在首次启动或安装后台时设置 `QUOTA_POCKET_FAKE_IP=1`。它仅允许域名解析到代理合成地址，不放行 localhost、直接 IP 或其他内网地址；默认关闭。已有后台启用该选项时需在重启的环境中保留。

## 手机展示与诊断

运行手机脚本 → 调整展示账户 → 勾选、排序。小、中、大号每组显示 1、2、4 个账户，超出时按选择顺序轮换；三种尺寸都逐窗口显示重置时间。时间缺失会明确提示，过期时间显示待确认。选择保存在手机，后续 Mac 快照不会覆盖。

Mac“高级：限制允许同步的账户”控制候选范围。撤回账户需要手机收到新快照；离线手机仍可能保留旧缓存。同一 Mac 的组件共享手机选择，可用 `codex` / `claude` 参数筛选。

脚本菜单“同步诊断 / 重新读取”显示读取来源、失败阶段、快照生成时间、Mac 采集完成时间和账户成功采集时间。重新读取只检查手机已到达的数据，不能强制 Apple 同步或唤醒 Mac。

失败保留旧值并明确标记采集失败；读取旧缓存不改变真实采集时间。iCloud 文件落后时使用较新的缓存；重置时间已到不代表额度自动恢复为 100%。

“Mac 已写入”不等于“iPhone 已收到”。iCloud 传输和 iOS 桌面刷新由系统调度，不能保证每 5 分钟刷新。已有真实 iPhone 端到端更新验证；锁屏、低电量、网络切换和睡眠唤醒仍需分别验收。

## 测试

在源码目录运行：

```sh
npm ci --ignore-scripts
npm test
```

统一运行 Python、Scriptable 契约及采集到已安装脚本的贯穿测试。上游异常、白名单过滤、旧快照、离线缓存、范围撤回都在自动化覆盖中。模拟器不能代替 iPhone 渲染和系统调度测试。测试产物保留在 `output/test-runs`，需要清理时自行处理。

## 范围

当前只支持 Mac 采集、iCloud 同步和 iPhone Scriptable。仓库仍有尚未拆除的旧协议兼容实现，不属于本测试版支持范围。当前计划见 [MAC-IPHONE-ICLOUD-PLAN.md](MAC-IPHONE-ICLOUD-PLAN.md)。

轮换以 15 分钟为时间窗口，按筛选后的手机选择顺序分组，末组不足时保留空格。显示当前组数；实际切换发生在 iOS 再次运行脚本时，不能保证桌面准时每 15 分钟变化。同一时间内重新运行保持同组。

## 文档与反馈

- [让本地 Agent 帮你安装](#agent-install)
- [连接与同步排查](CONNECTIVITY.md)
- [小组件刷新与轮换机制](WIDGET-REFRESH-RESEARCH.md)
- [验证记录与已知限制](VALIDATION.md)
- [v0.1.3 发布说明](RELEASE-NOTES.md)

欢迎通过 GitHub Issues 提交问题或建议。请提供 macOS / iOS 版本、操作步骤及已脱敏的错误信息；不要附上密钥、Token、带管理凭证的网址或真实账户快照。提交代码前请运行 `npm test`。

## 许可与致谢

项目采用 [MIT License](LICENSE)。感谢 [Scriptable](https://scriptable.app/)、[CC Switch](https://github.com/farion1231/cc-switch)、[CodexBar](https://github.com/steipete/CodexBar) 及所使用的开源依赖。随附第三方组件的许可证保留在对应目录中。

本项目为社区独立项目，与相关 AI 服务提供商没有官方关联。
