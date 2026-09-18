# 电脑与 iPhone 的连接与排查

唯一链路：Mac / Windows 采集 → 字段白名单 → 用户 iCloud Drive → iPhone Scriptable。

## 配置条件

电脑和 iPhone 登录同一个 Apple 账户并开启 iCloud Drive。iPhone 先[下载安装 Scriptable](https://apps.apple.com/app/scriptable/id1405459188)，首次打开并允许 iCloud 后，在 电脑管理页按“一步步配置”完成账户连接、额度确认、iCloud 写入和手机确认。

手机不需要填写 电脑地址。API Key、OAuth Token 和登录凭证保留在 电脑；iCloud 只保存筛选后的额度展示快照及小组件脚本。

## 文件与安装身份

每次安装的快照位于 Scriptable iCloud Documents 下的 `QuotaPocket/<安装 UUID>/snapshot.json`，专属脚本名包含安装 ID 前八位。手机选择和缓存按完整安装 ID 隔离。

正常采集会更新快照。脚本缺失或版本变化时，采集器会重新安装它。因此要彻底移除当前安装，应先在 电脑停用 iCloud 同步，再手动清理手机脚本和小组件。停用不会删除文件。

不要通过删除 电脑的账户状态来清理手机：新状态会生成新的安装 ID，旧云端文件仍会保留。多台 电脑或多个状态目录也会生成不同脚本。清理前核对管理页显示的专属脚本名称，只保留自己仍在使用的安装。

## 按顺序排查

1. 在 电脑确认账户采集状态和真实采集时间；失败时先处理登录或数据源连接。
2. 检查 iCloud 最近写入状态。后台权限错误时，停用后台并恢复手动采集，见[首页](../README.md)。
3. 在 iPhone 打开对应脚本，选择“同步诊断 / 重新读取”，核对快照与账户时间。
4. 核对桌面组件选择的是同一个脚本。前台读取成功后，桌面重绘仍由 iOS 调度。

电脑已写入不等于 iPhone 已收到。重新读取不能强制 Apple 同步、唤醒 电脑或向上游查询。离线时显示旧缓存及原始时间；撤回账户需要手机收到新快照才会生效。

参考：[Scriptable FileManager](https://docs.scriptable.app/filemanager/)、[刷新机制](WIDGET-REFRESH-RESEARCH.md)。
