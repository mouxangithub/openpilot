# 通用 GM 系（Chevrolet · Cadillac · GMC · Buick）

brand 为 gm / chevrolet / cadillac / gmc / buick 时关注：

| Param / 能力 | 说明 |
|--------------|------|
| `dp_lat_alka` | 全速域横向 |
| `dp_lon_acm` / `dp_lon_aem` | 纵向滑行与加速性格 |
| `OpenpilotEnabledToggle` | 总开关 |

Super Cruise / 原厂 ADAS 冲突时：先 `trip_review` 看事件，必要时暂时关闭 ALKA 排查。
固件指纹变更后跑 `car_porting_auto_fingerprint` 更新草稿。
