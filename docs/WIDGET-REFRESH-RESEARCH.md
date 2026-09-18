# Scriptable 小组件刷新机制

## 数据为什么不会同时更新

额度更新要经过三个独立阶段：Mac 查询上游、iCloud 传输文件、iOS 运行 Scriptable 并重绘桌面。

Mac 默认每 5 分钟采集一次，用户可修改周期。睡眠、关机或进程停止时不会继续采集。iCloud 到达时间与桌面重绘均由系统调度，不能承诺固定刷新间隔。

Scriptable 的 `refreshAfterDate` 表示最早允许刷新时间，并不保证该时刻执行。Apple 描述的常见刷新预算随使用情况变化，不能当作定时器。

## 轮换与重新读取

小、中、大组件分别按 1、2、4 个账户分组。每 15 分钟为一个轮换时间窗口，下次执行脚本时根据当前时间选组；末组不足时保留空格。系统延迟执行时，桌面可能停留在上一组，也可能跳过某一组。

“同步诊断 / 重新读取”会检查手机可用的数据，不能直接要求 Mac 查询或强制 iCloud 同步。前台脚本与桌面视图更新是不同阶段。

## 验证方法

分别记录 Mac 采集完成、Mac 写入、iPhone 读取、桌面重绘时间。睡眠唤醒、锁屏、低电量、网络切换与离线恢复需要真机验证，不能用模拟测试替代。

## 官方依据

- [Apple：Keeping a widget up to date](https://developer.apple.com/documentation/widgetkit/keeping-a-widget-up-to-date)
- [Scriptable：ListWidget.refreshAfterDate](https://docs.scriptable.app/listwidget/#refreshafterdate)
- [Scriptable：FileManager](https://docs.scriptable.app/filemanager/)
