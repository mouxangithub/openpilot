# 调参后验证闭环

每次写入 `dp_*` 或套用预设后，必须走完验证链：

1. **改前快照**：`save_tune_snapshot(label="before_xxx")` 或依赖 `write_params` 自动快照
2. **同路段复测**：再跑一条相似路线（速度/路段尽量一致）
3. **量化评分**：`score_tune_session(route_before, route_after)` — 评分下降则拒绝保留
4. **A/B 对比**：`compare_tune_ab` + `route_event_timeline`（若有 disengage）
5. **回归护栏**：`write_params` / `apply_tune_from_route` 传 `route_before` + `route_after` 自动拦截劣化
6. **调参护照**：`list_tune_passport` 查看历史改动
7. **回滚**：`restore_tune_snapshot(confirm=true)`
8. **审计**：`list_audit_trail`

工作流：`post_tune_validation`（快捷动作「调参验证」）

参数监视：`manage_param_watchlist` + 定时 `check_param_watchlist_offroad`
