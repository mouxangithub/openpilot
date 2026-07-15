# Nissan / Infiniti 特调

brand=nissan 或 infiniti 时：

- 横向不稳：查 `dp_lat_alka`、`dp_lat_offset_cm`，对比 `route_event_timeline`
- 纵向跟车：查 `dp_lon_acm`、`LongitudinalPersonality`
- 用 `live_can_capture` 辅助确认雷达/CAN 异常（只读）
- 改参后 `compare_tune_ab` 验证
