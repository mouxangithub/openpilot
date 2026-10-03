# 2026-10 carrot 导航的统一控制设计（限速 / 弯道 / 红绿灯）

## 一、为什么关闭 OSM 后 carrot 导航的限速和弯道数据消失

**结论：OSM 是兜底数据源，不是 carrot 数据的依赖。**

数据源分工（`speed_limit_resolver.py` / `carrot_man.py`）：

| 数据 | 来源 | 说明 |
|---|---|---|
| 限速（道路等级） | **carrot 手机**（`carrotManSP.nRoadLimitSpeed`）**或** OSM（`liveMapDataSP`） | carrot 优先：写入同一个 `map` 源，**无论高低都覆盖 OSM**（旧版是 lower-only，已改） |
| 限速（SDI 摄像头） | carrot 手机（`xSpdLimit` + `xSpdDist`） | 按 `LIMIT_ADAPT_ACC` 提前制动 |
| 弯道减速（ATC/turn/route） | **carrot 手机**（`atcSpeed` / `vTurnSpeedMs` / `routeSpeed`） | `navRoute` 由 carrot_man 从**导航路径折线**转换，纯几何曲率，**不需要 OSM** |
| 道路名 | OSM（`liveMapDataSP.roadName`） | 仅 OSM |

**所以**：关 OSM 后，**只有 OSM 这一个源消失**。用户观察到"限速和弯道都没了"，实际是**当时没有 carrot 手机数据源**（未连手机/未投影导航）——OSM 是唯一的兜底。修法不是改 OSM 开关，而是**确保 carrot 数据源接入时优先**（已实现）。

## 二、统一控制的现状与目标

### SLA 模式（`speed_limit/common.py`）

```python
class Mode(IntEnumBase):
  off = 0          # 关闭
  information = 1  # 只显示
  warning = 2      # 警告
  assist = 3       # 实际控制
```

### 三类功能的现状（不统一）

| 功能 | 现有开关 | 是否跟随 SLA 模式 |
|---|---|---|
| 限速标志 | `SpeedLimitMode` | ✅ **已统一**：`speed_limit_assist.enabled = (SpeedLimitMode == assist)`；carrot 限速折叠进 `map` 源供 UI 显示 |
| 弯道减速 | `CarrotMapDecelEnabled`（独立布尔） | ❌ 独立 |
| 红绿灯 | `CarrotTrafficLightFusionEnabled`（默认 0）+ `TrafficLightNavCautionOnly`（默认 1）+ `TrafficLightDetectMode`（0/1/2） | ❌ 独立（三个开关） |

弯道减速的既有设计理由（`map_controller._update_carrot_map_decel` 注释）：SLA 管"限速标志"（绝对约束），导航驱动的前方减速归 `SmartCruiseControlMap`（jerk/accel 限制的前视模型）。**架构上分开是合理的，但用户体验上三套开关难懂。**

## 三、统一方案

**核心：让弯道与红绿灯跟随 `SpeedLimitMode`，且新模式只做"降级"，不新增控制。**

```
SpeedLimitMode = assist(3)      → 限速减速 + 弯道减速 + 红绿灯停走（= 现状行为）
SpeedLimitMode = warning(2)     → 全部只警告（UI/声音，不动车）
SpeedLimitMode = information(1) → 全部只显示（UI 数据）
SpeedLimitMode = off(0)         → carrot 导航数据不参与
```

**关键设计约束：assist 档位下的控制行为与今天完全一致**——统一只改变 warning/information/off 的行为（从"仍然控制"变为"不控制"）。这样**不引入新的控车风险**，只是给用户一个更细的控制梯度。

### 实现点

1. **弯道**（`smart_cruise_control/map_controller.py`）
   - `_update_carrot_map_decel` 入口加模式判断：非 `assist` 时**不折叠 `v_target`**（warning/information 仍发布数据供 UI）
   - 保留 `CarrotMapDecelEnabled` 作为总开关（AND 语义）
2. **红绿灯**（`selfdrive/controls/lib/traffic_light_fusion.py`）
   - 模式映射：`assist` → 现有 fusion 行为；`warning` → 等价于今天的 `TrafficLightNavCautionOnly=1`（只警告）；`information` → 只发布状态；`off` → 不参与
   - 保留 `CarrotTrafficLightFusionEnabled` / `TrafficLightDetectMode` 作为细调
3. **UI**：SLA 设置页的档位说明补充"同时管理限速/弯道/红绿灯"；`carrotManSP.desiredSource` 已发布减速原因（`deceleration_source.py` 的标签体系），warning/information 档位下可直接用于显示
4. **过渡策略**：新增 `CarrotNaviUnifiedModeEnabled`（默认 **0** = 今天的行为），打开后跟随 `SpeedLimitMode`——避免升级即改变现有用户行为

## 四、与 CarrotPilot (E:/cp) 的对比

**核心导航能力 sp 已比 cp 更完整**（行数对比）：

| 文件 | cp | sp |
|---|---|---|
| carrot_man.py | 2333 | **3250** |
| carrot_serv.py | 1822 | **2000** |
| carrot_navi.py | 1331 | **1428** |
| carrot_navi_control.py | 292 | **316** |
| curve_speed.py | 148 | **175** |
| traffic_stop.py | 121 | **141** |
| t_follow.py | 42 | **69** |

**cp 独有、sp 未移植的**（均与"限速/弯道/红绿灯统一"无关）：

| 文件 | 行数 | 内容 | 借鉴价值 |
|---|---|---|---|
| `driving_mode.py` | 108 | 驾驶模式（影响纵向策略档位） | 中——可作为统一档位的参考实现 |
| `cruise_gap.py` | 15 | 巡航车距 | 低 |
| `cweb_push.py` / `web_upload.py` | 97+ | 数据推送/上传 | 低（sp 有 webui/uploader） |
| `cluster_*.py` | — | 仪表盘启动器 | 视硬件策略 |
| `radar_lead_*.py` / `validate_radar_lead_model.py` | — | 雷达前车工具链 | 单独立项 |

**结论**：**"统一控制"不是从 cp 学来的缺失功能**——cp 同样是分散开关（它没有统一的模式抽象）。这是 sp 自己的架构改进机会；cp 可借鉴的只有 `driving_mode.py` 的档位组织思路。

## 五、风险与验证要求

- 涉及**纵向控车**（弯道减速、红绿灯停走）→ **必须实车验证**（SOP：控车改动需 onroad 确认）
- 建议顺序：① 实现模式判断（默认 `CarrotNaviUnifiedModeEnabled=0`，行为不变）→ ② offroad 单测（模式映射）→ ③ 实车验证 warning/information 档位不动车 → ④ 实车验证 assist 档位行为与今天一致 → ⑤ 默认值再评估
- **不修改** `SpeedLimitMode` 的既有语义（SLA 标志控制不受影响）
