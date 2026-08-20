# 丰田 openpilot 特调

brand=toyota / lexus 时：

| Param | 说明 |
|-------|------|
| `ToyotaStopAndGoHack` | 停走辅助 |
| `ToyotaEnforceStockLongitudinal` | 强制原厂纵向 |
| `Mads` | 全速域横向（替代 DP 的 dp_lat_alka 思路） |
| `MadsMainCruiseAllowed` | 丰田等：MAIN 触发 MADS 横向 |

**MADS 横向 / LKAS 故障** → 技能 **mads-lateral-troubleshoot**，工具 **`diagnose_mads_lateral`**
| `LagdToggle` | 转向延迟学习 |

工具：`list_sp_settings`、`apply_sp_tune_preset` → `sp_toyota_sng` / `sp_toyota_stock_lon`

SecOC 车见 **secoc-toyota** 技能。TSS 世代不同行为差异大，写前确认 fingerprint。

DP 遗留：`dp_toyota_*` 见 **dp-tuning**（若存在）。
