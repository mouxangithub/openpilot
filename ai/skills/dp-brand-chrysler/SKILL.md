# Chrysler / Stellantis 系特调

brand=chrysler、jeep、dodge、ram、fiat 时：

- 关注 `dp_lat_alka` 与跟车距离相关 `dp_lon_*`
- engage 问题走 `engage_triage` 工作流
- 路线复盘：`trip_review` + `route_event_timeline`
- 调参验证：`score_tune_session` + `restore_tune_snapshot` 回滚预案
