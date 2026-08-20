# CAN 解读

## 看路线（第一步）

查本机行车录像 / Cabana 回放路线时，**必须用工具** `list_drive_routes` 或 `cabana_list_routes`（与 Cabana UI、`GET /api/cabana/routes` 同源，只列含 qlog/rlog 的路线）。

**禁止**用 `run_shell` / `ls` 猜路线目录——路径因设备而异（车机多为 `/data/media/0/realdata`）。

选定路线后再用：`analyze_route_summary`、`read_qlog_segment`、`route_can_stats`。

## 信号与报文

`cabana_explain_signal`、`cabana_analyze`、`read_qlog_segment`、`route_can_stats`
