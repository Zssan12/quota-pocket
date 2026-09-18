# 文档与开发

[返回首页](../README.md) · [English](../README.en.md)

## 使用指南

- [Mac 后台与升级](MAC.md)
- [Windows 使用指南](WINDOWS.md)
- [iCloud 同步排查](CONNECTIVITY.md)
- [让本地 AI 助手安装](AGENT-INSTALL.md) / [English](AGENT-INSTALL.en.md)
- [小组件刷新机制](WIDGET-REFRESH-RESEARCH.md)
- [版本记录](RELEASE-NOTES.md)

## 当前代码与数据流

`server.py` 提供本机管理页和采集调度，通过 `adapters.py` 读取额度、`subscription_auth.py` 管理独立订阅凭证。`icloud_sync.py` 只导出白名单展示字段与 `widgets/Quota-Pocket.js`；iPhone 的 Scriptable 读取个人 iCloud 文件并绘制组件。凭证留在电脑，失败保留旧额度和原成功时间。

`web/` 是配置网页，`install.py` 和 `windows_launcher.py` 是平台启动入口。`tests/` 验证采集、账号隔离、安装、同步与小组件；运行方法见[首页](../README.md#更多)。

当前路线是 Mac / Windows → 个人 iCloud → iPhone Scriptable。Windows 订阅与后台启动、iCloud 送达时间、iOS 桌面刷新仍需对应设备实测；自动化测试不能代替这些验证。

## 历史材料

[旧实现计划](archive/MAC-IPHONE-ICLOUD-PLAN.md)、[早期验证记录](archive/VALIDATION.md)、[数据源调研](archive/RESEARCH.md)仅供追溯，不代表最新支持范围。

[托管、中继与 Widgeto 原型](../archive/hosted/README.md)已退出当前运行及安装路径，其测试也不再计入默认测试。新方案若重新采用它们，需单独审查和验证。

## 最近验证

2026-09-18：`npm test` 通过 123 项 Python 测试及 Scriptable/setup 测试；文档相对链接检查通过。本次归档 14 项旧托管测试，新增 3 项当前安装边界测试，覆盖历史托管配置保留但不加载、旧接口返回 404，以及新安装不含归档资源仍能启动。未重新执行手机实机验收。
