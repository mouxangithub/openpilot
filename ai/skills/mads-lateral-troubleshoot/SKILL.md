# MADS 横向 / LKAS 故障排查

用户报 **「控制不匹配：横向」**、**「LKAS故障」**、**MAIN+MADS 不控横向**、**MADS 开就报错** 时启用本技能。

## 先调工具（按顺序）

1. **`diagnose_mads_lateral`** — 结构化分诊（事件 + MADS 参数 + 修复清单）
2. **`get_mads_settings`** — Mads / MadsMainCruiseAllowed / MadsSteeringMode
3. **`read_onroad_events`** 或 **`trip_review`** — 确认事件名
4. **`grep_log`** — `mads|lateral|LKAS|controlsMismatch|heartbeat|pandad`
5. 丰田 SecOC → 另读 **secoc-toyota** 技能

## 两种报错不要混

| UI 文案 | 事件名 | 根因层 | 典型修复 |
|---------|--------|--------|----------|
| 控制不匹配：横向 | `controlsMismatchLateral` | Python `mads.py` `data_sample()` vs Panda `controlsAllowedLateral` | 禁用 `data_sample()`；恢复 `pandad` MADS heartbeat |
| LKAS故障：请重启车辆 | `steerTempUnavailable` / `steerUnavailable` | 丰田 EPS `LKA_STATE`；软件发 LKA 但 Panda 拦截 TX | `opendbc` `mads.h` MAIN 电平保持 + **刷 Panda** |

## 故障链（MAIN + MADS，丰田等无独立 MADS 键）

```
MAIN 上升沿 → Panda 短暂放行 controls_allowed_lateral
→ pandad heartbeat 滞后 / 不同步
→ mads.h 连续 3 次撤权
→ MAIN 仍亮但无法再次请求（仅上升沿）
→ selfdrived 仍 mads.active → 发 STEERING_LKA
→ Panda 拦截 → EPS LKA_STATE 故障
```

## master-c3 已合入修复（对照用户分支）

| 层 | 文件 | 作用 | 是否刷 Panda |
|----|------|------|-------------|
| 误报 | `sunnypilot/mads/mads.py` | `data_sample()` 禁用 | 否 |
| heartbeat | `selfdrive/pandad/pandad.cc` | 按刹车模式 `active`/`enabled` + 读 `carParams` | 否 |
| 固件 | `opendbc/safety/sunnypilot/mads.h` | `mads_acc_main_lateral_latch()` MAIN 保持横向 | **是** |

固件关键逻辑：`mads_acc_main_lateral_latch()` — 无 MADS 物理键时 MAIN 亮则持续请求横向；heartbeat 短暂不同步不立刻撤权。

## 与旧 fork ALKA 的区别

部分旧 fork 用 **`dp_lat_alka`** + `lkas_on = acc_main_on`（电平），**无** `controls_allowed_lateral` / MADS heartbeat。  
本安装树用 **MADS**；要在 MADS 下达到「按 MAIN 横控」，靠 `mads.h` 补丁学 ALKA 电平思路，不是直接开 `dp_lat_alka`。

## 用户操作确认

- 丰田：**巡航 MAIN**（不是 LDA 键）+ 设置里 **MADS 开** + **与主巡航切换** 默认开
- 默认 **MadsSteeringMode=0**（Remain Active）→ pandad heartbeat 用 `mads.enabled`
- **Disengage(2)** 模式 → heartbeat 用 `mads.active`

## 排除步骤（给用户）

1. **只编译未刷固件** → `mads.h` 不生效；跑 `python selfdrive/pandad/pandad.py`
2. **events 只有 controlsMismatchLateral** → 先确认 `mads.py` 已禁 `data_sample()`，重编 selfdrived
3. **events 有 steerTempUnavailable + MAIN+MADS** → 查 opendbc 是否含 `mads_acc_main_lateral_latch`，刷 Panda
4. **MADS 关 + ACC 跟车正常** → 预期；问题在 MADS 解耦层
5. **MADS 关 + MAIN 也不控** → 查是否未开 ACC / 未 engage

## 写入建议（静止）

- 不要乱关 Mads 除非用户要求；优先确认固件与 pandad
- `MadsSteeringMode`：排查时可建议 **0 Remain Active**（默认）
- 勿把 `dp_lat_alka` 与 MADS 同时当主方案混用

## 相关技能

- **sp-brand-toyota** — 丰田 Param
- **sunnypilot-settings** — MADS 读写工具
- **safety-policy** — 行车中只读
