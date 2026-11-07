# 路线分析

1. **列路线**：`list_drive_routes` 或 `cabana_list_routes`（与 Cabana 路线列表一致）
2. **摘要**：`analyze_route_summary`（路线名来自上一步）
3. **深入**：`plotjuggler_data_summary`、`read_qlog_segment`、`suggest_tune_from_route`、`apply_tune_from_route`

勿用 shell `ls` 代替路线列表工具。
