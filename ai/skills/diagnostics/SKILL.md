# 系统诊断技能

## 快速健康检查（任意状态可读）

1. `get_vehicle_state` — vEgo, enabled, events  
2. `read_params` — Version, dp_dev_last_log  
3. `device_health` / `get_host_environment` — 车机型号（`tici`/`tizi`/`mici`）、pandad 变体  
4. 若静止：`run_shell` — uptime, free, df  

## Manager / 崩溃

- `read_params`: dp_dev_last_log  
- `grep_log` 或静止时 `run_shell`: **grep_log_errors**（latest.log 错误摘要）  
- 静止时 `run_shell`: journalctl_manager  
- 需要重启 UI：`restart_ui`（用户开启工具 + 静止）

## PC 开发命令 → 车机替代

| PC 开发机 | 车机 op助手 |
|------------|----------|
| `tail -f /tmp/logcat.log` | grep_log / grep_log_errors / read_manager_log |
| `grep -i error` 日志 | grep_log_errors |
| `cereal messaging dump carState` | get_vehicle_state / get_full_vehicle_state |
| PlotJuggler | `plotjuggler_data_summary` / `route_time_series`；PC：`tools/plotjuggler/juggle.py` |
| comma connect | `comma_auth_status` / `read_bootlog` |
| `python3 common/params.py` | read_params / param_dump（run_shell） |

## AI 服务本身

- `read_params`: ai_provider, ai_model, ai_usage_log  
- Web `:5090` 不通 → aid 进程、防火墙、同网段  
- API 400 → 缺 ai_api_key / model  

## 性能

- `free` / `df` 磁盘满会导致 loggerd 失败  
- `DisableLogging` 可缓解但影响回放  

## 输出格式

给用户：**现象 → 证据（工具输出）→ 可能原因 → 建议操作（区分行驶/静止）**
