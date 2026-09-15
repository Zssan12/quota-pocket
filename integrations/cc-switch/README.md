# CC Switch 额度缓存导出桥接（实验归档）

本方案已退出第一版默认路线。日常使用推荐每 10 分钟独立查询，避免维护修改版 CC Switch。以下内容仅供源码研究，未应用到本机安装版。

这是提供给 **CC Switch 源码构建**的可选补丁，不是官方安装包已有的接口。当前电脑未安装 Rust 工具链，因此只完成补丁应用检查，**尚未编译或在 CC Switch 真机验证**。没有修改已安装的 CC Switch，也没有向上游发布代码。

固定基线：[`1d5d90f4aba88447d422a16cdec5282ec5331fd7`](https://github.com/farion1231/cc-switch/tree/1d5d90f4aba88447d422a16cdec5282ec5331fd7)。补丁包含 `UsageCache` 的写入/失效钩子和 `pocket_export.rs` 模块；源文件单独保留，便于审阅。上游上下文采用 MIT，许可见 `UPSTREAM-LICENSE`。

## 为什么使用文件

CC Switch 已经负责凭证、查询和刷新。桥接只在缓存变化时额外写一份经过字段筛选的本地 JSON，不新增端口、网络请求、登录或轮询。额度口袋每 5 秒检查文件是否变化，变化后读取；额度口袋再将白名单快照写入 iCloud，供 iPhone Scriptable 读取。

因此 CC Switch 若每 10 分钟查询，平台请求仍只有原来的那一份。没有查询过的 Provider 不会凭空出现；并不为了补齐列表再发请求。脚本额度、原生订阅与托管 Codex 账户各自保留独立标识。

## 应用与构建

先具备上游要求的 Rust、Node、pnpm 及操作系统构建依赖。在独立源码目录中执行，**不要覆盖当前安装目录**：

```sh
git clone https://github.com/farion1231/cc-switch.git cc-switch-quota-export
cd cc-switch-quota-export
git checkout 1d5d90f4aba88447d422a16cdec5282ec5331fd7
git apply --check /absolute/path/quota-pocket/integrations/cc-switch/cache-export.patch
git apply /absolute/path/quota-pocket/integrations/cc-switch/cache-export.patch
pnpm install --frozen-lockfile
cargo test --manifest-path src-tauri/Cargo.toml --lib services::usage_cache
pnpm build
```

`/absolute/path` 换成实际路径。上面的 Rust 测试命令是待执行验证步骤，不代表本项目已经通过完整 CC Switch 构建。

退出原来的 CC Switch 实例，避免单实例机制将启动转给旧进程。通过环境变量启动补丁版本（macOS / Linux 示例）：

```sh
CC_SWITCH_QUOTA_EXPORT="$HOME/.cc-switch/quota-pocket.json" ./src-tauri/target/release/cc-switch
```

路径必须绝对且父目录已存在。Windows 使用 PowerShell `$env:CC_SWITCH_QUOTA_EXPORT` 指定当前用户私有目录中的文件，再启动构建的 `.exe`。不设置环境变量时，导出完全关闭。没有修改系统环境变量或开机启动项。

在额度口袋选择 CC Switch → **读取缓存**，文件路径与上述变量一致。在 CC Switch 正常查询一次后，额度口袋应在约 5 秒内读到；手机实际刷新仍由其系统调度。

## 快照协议 v1

```json
{
  "schemaVersion": 1,
  "source": "cc-switch-usage-cache",
  "exportedAt": 1800000000,
  "entries": [
    {
      "kind": "script",
      "appType": "codex",
      "providerId": "local-provider-id",
      "observedAt": 1800000000,
      "success": true,
      "data": [{"planName": "账户余额", "remaining": 42.3, "unit": "CNY", "isValid": true}]
    },
    {
      "kind": "subscription",
      "appType": "claude",
      "accountId": "",
      "observedAt": 1800000000,
      "success": true,
      "tiers": [{"name": "five_hour", "utilization": 28, "resetsAt": null}]
    }
  ]
}
```

这只是协议示例，不是账户数据。`codex_oauth` 使用非空本地 `accountId` 隔离托管账户。

- `observedAt` 是每条额度的原始时间。脚本采用缓存收到结果的时间；订阅优先使用 CC Switch 的 `queried_at`（毫秒转秒），没有时使用收到结果的时间。
- `exportedAt` 是文件写入时间，不参与更新某条额度的采集时间。
- 只导出额度字段与本地关联 ID。不导出 Key、Cookie、请求头、原始错误、凭证状态文本、额外用量消费或会话记录。名称来自额度口袋对数据库展示字段的只读查询。
- 同目录临时文件 + 原子替换，Unix 权限 `0600`；Windows 应使用自己的私有用户目录。临时文件由 `tempfile` 管理。
- 缓存失效会移除对应条目；整个缓存失效或进程重新启动时输出空快照。失败写入不会影响 CC Switch 原来的查询，读端保留旧值和旧时间。
- 缓存模式缺文件、解析失败、未知版本时明确报错，**从不回退到 HTTP 查询**。

## 完整验收尚待执行

1. 编译并运行上游缓存与导出模块的 Rust 测试。
2. 在补丁版 CC Switch 中查询一次，确认导出文件只包含允许字段。
3. 对比上游请求数：打开/刷新额度口袋、刷新手机，均不增加 Provider 请求。
4. 验证失败、禁用查询、删除 Provider、账号切换和应用重启；确认不会跨账户展示，也不会把旧额度标为刚刚更新。
5. Windows / macOS 的文件替换与权限、后台运行另行实测。

由于补丁跟随指定源码版本，生产分发前应完成上述验收；长期优先争取上游提供稳定快照导出，避免用户长期维护自己的 CC Switch 构建。
