# 已归档：托管、中继与 Widgeto 原型

这些文件保留早期实验，不是当前产品功能，不随安装器分发，也不由默认测试执行。当前使用方式见[项目首页](../../README.md)。

- `hosted_server.py`、`hosted_sync.py` 与 `web/`：托管快照及 Widgeto 配对原型。
- `relay_server.py`、`sync_crypto.mjs` 与 `vendor/`：早期加密中继实验及其依赖，许可证随源码保留。
- `widgeto.py`：Widgeto 模板与额度格式转换。
- `tests/test_hosted.py`：对应的历史测试。

项目选择个人 iCloud 同步，避免要求用户部署服务器、配置公网或额外 VPN。当前采集器不再导入、初始化、启动或提供托管接口；历史 `hosted-sync.json` 不会被读取、上传或删除。

这里保存的是历史材料，移动后未承诺独立可运行。不要直接部署；重新启用前需检查导入路径、静态资源、认证和部署边界，并补充实机验证。
