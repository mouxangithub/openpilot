# 路线与日志诊断

1. `list_drive_routes` → 最近路线名
2. `analyze_route_summary` → 段目录、大小、qlog/rlog 预览
3. **`trip_review`** → 一键复盘（events 分诊、SecOC 提示、调优快照、建议）
4. `route_time_series` / `plotjuggler_data_summary` → 时序与统计（无需 PC PlotJuggler）
5. `route_video_info` + `route_fetch_frame` → 视频帧（本地或 comma API）
6. `read_qlog_segment` → CAN / 状态片段
7. `grep_log` / `read_manager_log` / `read_bootlog` → 错误模式
8. CAN 深度分析 → Cabana 工具

PC 专用（技能指引，不车机执行）：`tools/replay/replay`、`tools/plotjuggler/juggle.py`、桌面 `tools/cabana/cabana` — **在 PC dev 上改用** `get_host_environment` + `pc_launch_*`。
