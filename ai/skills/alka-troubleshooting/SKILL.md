# ALKA 排查

1. `read_params` → `dp_lat_alka`
2. `list_dp_settings` → 确认当前品牌可见 ALKA 项
3. `get_vehicle_state` → brand、fingerprint、enabled
4. 本田/丰田/VAG 特调见品牌技能

**不生效常见原因**：品牌不支持、未 OP 纵向、用户踩刹车退出、车型指纹错误。

建议静止时开启，reengage 后测试。
