# Mac 后台与升级

日常安装见 [首页](../README.md#开始使用)。以下为可选后台管理和升级说明。

Claude 独立登录的凭证到期时，采集器会调用官方 CLI 的 `/status` 完成续期，再读取本次登录的专属凭证；不发送聊天请求，也不读取默认 Claude Code 账户。请保留 Claude CLI；若 macOS 提示访问额度口袋专属钥匙串条目，请允许。续期失败会保留凭证和历史额度，页面标记查询失败。

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
