# MADS 设置

**Modular Assistive Driving System** — Settings → Steering → MADS。

## 工具

- `get_mads_settings` — 读取全部 MADS 相关 Param
- `set_mads_settings` — 写入（`confirm=true`，静止）

也可 `write_params` 写入下列键。

## Param

| Key | 说明 |
|-----|------|
| `Mads` | 总开关 |
| `MadsMainCruiseAllowed` | 与主巡航键联动 |
| `MadsUnifiedEngagementMode` | UEM 统一进入 |
| `MadsSteeringMode` | 0 保持 / 1 暂停 / 2 退出（踩刹车时） |

部分平台（Rivian、部分 Tesla）子选项受限，以 UI 为准。

## 预设

`apply_sp_tune_preset` → `sp_mads_full`、`sp_mads_brake_pause`
