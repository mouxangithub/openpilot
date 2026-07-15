# 现代 / 起亚（Hyundai · Kia）特调

brand=hyundai 或 kia 时关注：

| Param / 能力 | 说明 |
|--------------|------|
| `dp_lat_alka` | 全速域横向，韩系多数车型需先确认 LKAS 可用 |
| `LongitudinalPersonality` | 纵向性格，跟车顿挫时可调温和 |
| `dp_lon_acm` | 自适应滑行，高速跟车舒适 |
| `ExperimentalMode` | 部分平台实验纵向 |

排查 engage：`engage-troubleshooting` + `live_can_capture` 看 ADAS CAN 是否活跃。
写参前 `diff_params` 预览，用 `post-tune-validation` 闭环验证。
