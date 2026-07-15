# Mazda 特调

brand=mazda 时：

- 先读 `list_dp_settings` 与 `snapshot_tune_state`
- 弯道/画龙：`lat_maneuver_report` + `score_route_tune`
- 小改动原则：每次 `write_params` 不超过 3 项，配合回归护栏 `route_before`/`route_after`
- 记录到 `list_tune_passport` 便于回溯
