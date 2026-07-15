# CAN / Cabana 技能

## 入口

- Web 主界面 **📡** 打开 Cabana 抽屉（内嵌，非独立页）  
- API：`/api/cabana/*`（car, dbcs, dbc, routes, ws, analyze, explain）

## 使用场景

| 场景 | 做法 |
|------|------|
| 看实时 CAN | 连接实时 CAN → 表格 + 过滤 |
| 信号含义 | 点「AI 解释」列 |
| 当前片段 AI 分析 | **AI 分析片段** → 面板内结果，可再发到聊天 |
| 异常帧分析 | 选帧 →「发到聊天」或 analyze API |
| DBC 给 AI | **DBC→AI** → 聊天引导 `read_dbc_file` / `list_dbcs` |
| 曲线给 AI | 信号绘图后 **曲线→聊天**（含 ±30s 序列） |
| 离线路线 | 选 route → 回放（**无网页视频**，减轻卡顿） |
| 整段路线分析 | 「分析 route」→ 聊天带 DBC/进度/曲线；AI 调 `read_qlog_segment`、`analyze_route_summary` |

## 行驶中

- **只读**查看 CAN、AI 解释信号、**AI 分析片段** — 允许  
- 不要建议用户在驾驶时改 Param 或重启服务  

## 与调优联动

- 踏板/档位报文异常 → `vehicle-adaptation`  
- 雷达/前车相关 → 查 `dp_lon_ext_radar` 与纵向 Param  

## 聊天话术

引导用户：「打开 CAN 抽屉 → 连接或选路线回放 → **AI 分析片段** 或 **分析 route**」，需要 DBC 定义时点 **DBC→AI**；按时间段深挖用 `read_qlog_segment`。勿在网页内播 qlog 视频。
