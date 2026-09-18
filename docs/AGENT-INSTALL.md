# 让本地 AI 助手安装

[English](AGENT-INSTALL.en.md) · [返回首页](../README.md)

复制给能操作你电脑的 AI 助手；账户授权和 iPhone 操作由你完成。

```text
请在这台电脑安装并启动 Quota Pocket：
https://github.com/Zssan12/quota-pocket

先读 README，Windows 另读 docs/WINDOWS.md。检查 Python 3.9+、Node.js 20+，复用已有环境；缺少依赖时说明所需步骤。

在独立目录获取 main 分支源码，不覆盖已有账户或其他项目。
Mac：bash install.sh --source "$PWD"
Windows：npm ci --ignore-scripts，然后运行 start-windows.cmd。
已有 Mac 安装不会自动升级，请按 docs/MAC.md 核对运行副本。

验证本地配置页打开后，让我选择数据源并在官方页面授权。继续引导我确认额度、启用自己的 iCloud、先从 App Store 安装 Scriptable（https://apps.apple.com/app/scriptable/id1405459188），再运行生成脚本并添加组件。电脑写入不等于手机收到，需核对采集时间。

不要上传或打印密钥、Token、.state 或带凭证的网址，不修改原工具配置，不开启公网服务，不删除文件目录。后台自启动另行按需配置。
最后简述启动结果、以后如何打开，以及需要我完成的操作。
```
