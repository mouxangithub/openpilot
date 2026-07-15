# 斯巴鲁特调

brand=subaru 时关注：

| Param / 能力 | 说明 |
|--------------|------|
| `dp_lat_alka` | 全速域横向；EyeSight 车型注意 EPS 锁止事件 |
| `dp_lat_offset_cm` | 车道内偏移，山路可微调居中 |
| `LongitudinalPersonality` | 跟车节奏 |

若出现 `steerUnavailable`：先读 `read_onroad_events`，用 `car_porting_steering_accuracy` 看转向跟踪。
调参后用 `compare_tune_ab` 对比改前改后路线。
