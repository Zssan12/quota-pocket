# Windows → iCloud → iPhone

Windows 源码运行入口已加入；不是已完成全链路真机验收的 Windows 安装包。手机继续使用相同 Scriptable 脚本，包含账户选择、轮播、颜色及离线缓存。

## 安装与启动

1. 从 Microsoft Store 安装 Apple 的 iCloud，登录与 iPhone 相同的 Apple 账户，打开 iCloud Drive。手机安装、打开 Scriptable 并允许 iCloud。等待初始化结束。
2. 安装 Python 3.9+（推荐受支持的新版本）。使用 CC Switch 独立查询还需要 Node.js 20+ 和本机 CC Switch 账户配置。
3. 下载并解压仓库。在项目目录运行一次 `npm install --ignore-scripts` 安装查询脚本依赖。
4. 双击 `start-windows.cmd`，自动打开本机管理页。首次数据源默认关闭；在“连接数据源”选择现有 CC Switch 独立查询，先确认一个中转账户余额和成功采集时间正确。
5. “手机小组件”中启用 iCloud。脚本写入已存在的 Scriptable 容器；写入成功不是手机已收到。
6. 手机打开 Scriptable，运行页面显示的脚本名称，选择账户。添加 Scriptable 桌面组件并选择此脚本。

本版启动窗口须保持打开；Ctrl+C 停止采集。没有安装 Windows 计划任务或开机自启动。重新启动 Windows 后再次双击。已有服务时只打开管理页面，不重复采集。

## 路径

默认目录为 `%USERPROFILE%\iCloudDrive\iCloud~dk~simonbs~Scriptable`，不附加 Mac 的 `Documents`。仅检查这个明确路径，不扫描整盘、不创建 iCloud 容器。

自定义位置：在项目目录新建 UTF-8 文本 `windows-icloud-path.txt`，只写实际 Scriptable 容器的完整路径，不加引号，例如 `D:\iCloudDrive\iCloud~dk~simonbs~Scriptable`。重启采集器生效。文件已列入 Git 忽略。

也可在 PowerShell 中设置 `$env:QUOTA_POCKET_ICLOUD_DIR = '实际绝对路径'`，再执行 `py -3 -X utf8 server.py --open`。显式路径必须已存在，不可填普通 iCloud 根目录。路径覆盖不会迁移或删除旧云端文件。独立 Windows 安装生成新的安装 ID，保留 Mac 的脚本和快照。

## 验证范围

用户 2026-09-15～17 的验证：Windows 25H2 / iCloud 15.9.60.0 / PowerShell 7.6.5，Scriptable 容器文件正常网络连续两轮、手机蜂窝网络一轮读取了对应唯一 writeId 和 payload。未提供手机读取时间，不能计算延迟；锁屏、Windows 重启、桌面自动刷新未测。该证据只证明文件链路。

本次开发在 Mac 上运行 Windows 路径、UTF-8 中文快照、字段白名单、脚本生成和文件锁分支模拟测试。待 Windows 实测：服务启动、真实中转余额、独立 Claude/ChatGPT 授权与续期、云端脚本发现及手机桌面自动更新。不要把有代码入口当作所有 Provider 已适配；尤其 npm 安装的 CLI 包装脚本与原生 CLI 可执行文件行为可能不同。

真实验收：选一个账户，记录电脑成功采集时间、金额、快照 generatedAt，再在手机比较同账户、同币种、同采集时间。更新一次后重复比较，确认不是旧缓存。不要发送凭证文件；`.state/` 留在电脑本地，不能放入 iCloud。Windows 的 chmod 不是 POSIX 权限隔离，状态目录访问由 Windows 账户和 NTFS ACL 管理。
