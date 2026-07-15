# onroadEvents 解读

使用 `read_onroad_events` 获取当前事件列表。

## 严重级别

| 字段 | 含义 |
|------|------|
| `no_entry` | 无法进入 openpilot |
| `soft_disable` | 软退出，可恢复 |
| `immediate_disable` | 立即退出 |
| `permanent` | 需停车处理 |

## 排查顺序

1. 读 events → 按 `immediate_disable` / `no_entry` 优先
2. `grep_log` 搜索事件名
3. `read_manager_log` 看 manager 上下文
4. 结合 `vEgo`、`enabled` 判断是否行驶中

常见：摄像头遮挡、方向盘扭矩、刹车、档位、实验模式限制。
