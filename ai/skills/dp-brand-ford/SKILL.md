# Ford 系特调

brand=ford 或 lincoln 时：

- 先 `list_dp_settings` 对照纵向/横向开关
- 跟车与 ALKA 问题用 `plotjuggler_data_summary` + `car_porting_steering_accuracy`
- 调参闭环：`save_tune_snapshot` → `write_params` → `score_tune_session`
- 关注 `LongitudinalPersonality` 与 `dp_lat_alka` 组合
