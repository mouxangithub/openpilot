# 丰田转向角限幅放宽（大弯 / 闸道弯丝滑）

用户报 **「及时接管：转向超过限制」**、**丰田大弯/上下高速闸道弯转向不足**、**期望转角跟不上实际** 时启用本技能。

> ⚠️ 本节涉及**修改 opendbc 源码并重刷 panda 固件**，属高风险安全改动。改的是**车机控制实际执行**的代码，不是 Params。除非用户明确要求做代码级放宽，否则优先用**读取诊断**排查并解释根因，不要主动改源码。

## 一句话结论（先讲给用户）

提示来自 `EventName.steerSaturated`，**不是**绝对角度上限触发，而是**角速度速率**跟不上 + 控制器饱和判定的连锁。只把 `STEER_ANGLE_MAX` / `max_angle` 放宽到 180° 没用，必须**同时放宽角速度速率**，且 **前端 + panda 安全层必须严格一致**，否则 panda 直接丢帧。

## 诊断链路（先看，再决定是否改）

`selfdrived.py` 中 `steerSaturated` 需**三条件同时满足**：

```
undershooting = |desired横加| / |actual横加| > 1.2     # 转向不足
turning       = |desired横加| > 1.0                     # 确实在过弯
lac.saturated                                          # 控制器饱和
```

- `lac.saturated` 来自 `latcontrol_angle.py`：`|期望转角 - 实际转角| > 2.5°` 判饱和（`STEER_ANGLE_SATURATION_THRESHOLD`，速度相关，TODO 待改成速度相关）。
- 前两者用 `search_knowledge_base` / `read_onroad_events` / `trip_review` 确认。

**真正瓶颈**是角速度速率（每帧允许的最大角度变化），不是绝对角度上限。丰田 EPS 物理限速在 `values.py` 注释有载：**TSS 2.5 Camry / RAV4 内部扭矩速率 ~1500 units/sec**，低速 up≈15°/s、down≈18°/s 已贴近物理极限。

## 四层限幅从上到下

| 层 | 文件（opendbc） | 参数 | 说明 |
|----|------------------|------|------|
| 1 规划 | `selfdrive/controls/lib/drive_helpers.py` | `MAX_LATERAL_JERK`/`ACCEL` | 曲率源头，动它最危险 |
| 2 控制器 | `selfdrive/controls/lib/latcontrol_angle.py` | `STEER_ANGLE_SATURATION_THRESHOLD` | 2.5° 饱和判定 |
| 3 车控 | `opendbc/car/toyota/values.py` | `ANGLE_RATE_LIMIT_UP/DOWN` + `STEER_ANGLE_MAX` | **前端软件限速（改这）** |
| 4 安全 | `opendbc/safety/modes/toyota.h` | `angle_rate_*_lookup` + `max_angle` | **panda 硬限速（必须同步改）+ 刷固件** |

## 放宽操作步骤（源码级，用户明确要求时）

### 核心原则：前端与安全层必须严格一致

panda 的 `steer_angle_cmd_checks`（`opendbc/safety/lateral.h`）用安全层自己的速率算增量，**一旦前端命令角度变化超过安全层速率，该帧 LTA 转向指令会被 panda `tx=false` 整条丢弃**，比提示接管更严重。所以安全层速率必须 ≥ 前端速率。

### 改动点（三处对齐）

**A. `opendbc/car/toyota/values.py`** — `ANGLE_LIMITS`：
```python
# 低速段仅小幅上调(+17%)；中高速段可多放开(+20%)针对闸道弯
([5, 25], [0.35, 0.18]),   # UP（原 0.3/0.15）
([5, 25], [0.42, 0.30]),   # DOWN（原 0.36/0.26）
```

**B. `opendbc/safety/modes/toyota.h`** — `TOYOTA_ANGLE_STEERING_LIMITS`：
- `angle_rate_up_lookup` / `angle_rate_down_lookup` 与 A **同步相同数值**（`{5,25,25}` + 新速率）。
- `max_angle`：**务必换算正确**。`180° × 17.452007 = 3141`（不是 6283！6283 实际是 ±360°，远超 EPS 承受，会直接 PCS fault）。

**C. `opendbc/safety/tests/test_toyota.py`** — 同步测试期望，否则安全自检失败挡构建：
- `STEER_ANGLE_MAX = 180.0`
- `ANGLE_RATE_UP = [0.35, 0.18, 0.18]`、`ANGLE_RATE_DOWN = [0.42, 0.30, 0.30]`
- `MAX_LTA_ANGLE = 180.0`
- `ANGLE_RATE_BP = [5., 25., 25.]` 保持

### 安全红线（务必告知用户）

- **低速段不能猛放**：低速 `up≈15°/s` 已是 EPS 物理极限，再放大会触发 **PCS 预碰撞故障**（EPS 主动退出转向，比提示接管危险得多）。
- **安全层是 C 固件**：改了 `toyota.h` 必须**重新编译 panda 固件并刷入**才生效；前端 `values.py` 随 openpilot 热更新生效。本机（PC）无 scons 无法编译，需车机/CI 完成。
- 若实测出现 EPS/PCS fault → **立即回退低速段速率**，说明已越过物理极限。

## 已验证的推荐值（21款威兰达 PHEV / RAV4 Prime）

```
UP   : {5,25,25} → [0.35, 0.18]     # 低速 +17%，中高速 +20%
DOWN : {5,25,25} → [0.42, 0.30]     # 同上
max_angle = 3141                     # = 180.0°（与前端 STEER_ANGLE_MAX 一致）
```

此组值专门针对**上下高速闸道弯**（约 11~17 m/s 中速段）。若客户车型不同（Camry/其他 RAV4/TSS 世代），先确认 fingerprint 再据此档位微调。

## 若提示仍存在但已放宽速率

说明偏差仍 >2.5°，可微调控制器饱和阈值 `STEER_ANGLE_SATURATION_THRESHOLD`（`latcontrol_angle.py`，2.5→3.0）——这是**最安全的"少误报"旋钮**，只管提示不影响实际转向。纯提示容忍调整优先于继续放速率。

## 相关技能 / 文档

- **sp-brand-toyota** — 丰田 Param / MADS
- **mads-lateral-troubleshoot** — 横向/LKAS 故障（`controlsMismatchLateral`、`steerTempUnavailable`）
- **secoc-toyota** — 丰田 SecOC 加密 CAN
- **onroad-events** — `steerSaturated` 等事件解读
- **docs/PANDA_FLASH.md** — panda 固件刷写