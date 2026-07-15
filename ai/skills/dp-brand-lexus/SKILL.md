# 雷克萨斯 / 丰田系特调

brand=lexus 或 toyota 时：

- 优先启用 `secoc-toyota` 技能处理加密 CAN
- 关注 `dp_toyota_stock_lon`、`dp_toyota_tss1_sng`
- SecOC 未配置时禁止强行写 tune Param，先查 `lookup_secoc_tier` + `read_onroad_events`
- 调参后用 `score_tune_session` + `route_event_timeline` 验证 engage 稳定性
