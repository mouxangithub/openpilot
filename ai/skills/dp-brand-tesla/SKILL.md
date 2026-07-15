# Tesla 特调

brand=tesla 时：

| Param | 说明 |
|-------|------|
| `dp_lat_alka` | 全速域横向（视车型支持） |
| `LongitudinalPersonality` | 纵向性格 |
| `dp_lon_acm` | 舒适跟车模式 |

注意：

- Tesla 纵向多为原厂 ACC，确认 `openpilotLongitudinalControl` 状态后再调纵向人格
- 摄像头/模型问题用 `analyze_route_vision` + `route_event_timeline`
- 调参闭环：`save_tune_snapshot` → `write_params` → `score_tune_session`
