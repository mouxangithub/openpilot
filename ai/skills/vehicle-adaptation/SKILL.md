# 车辆适配技能

> 分步详解：`ai/docs/VEHICLE_ADAPTATION_GUIDE.md`（SecOC、锁止、人机闭环）

## 何时启用

新车型指纹、DBC、CarState/CarController 草稿、SecOC、无法识别车辆、控制无响应。

## 标准流程（四步）

1. **指纹识别** — CAN 特征 → `FINGERPRINTS` 字典  
2. **接口开发** — CarState 读状态、CarController 发控制  
3. **参数配置** — CarSpecs、`STEER_MAX`、`ACCEL_*`（代码库，非 Dashy 随意改）  
4. **安全验证** — 封闭场地路试  

| 概念 | 代码位置 | op助手工具 |
|------|----------|------------|
| CarInterface | `opendbc/car/*/interface.py` | `save_adaptation_draft` |
| CarState | `carstate.py` | `cabana_explain_signal`、`get_vehicle_state` |
| CarController | `carcontroller.py` | 草稿 + 人审扭矩/速率限幅 |
| **car_porting** | `tools/car_porting/` | `car_porting_auto_fingerprint`、`car_porting_test_route`、`car_porting_test_interfaces`、`car_porting_steering_accuracy` |

SecOC 车须先 Dashy 安装 SecOCKey（见适配指南 §二）。

---

## 1. 指纹识别

### 采集

| PC 开发机 | 车机 op助手 |
|-----------|-------------|
| manager 指纹模式、`can_printer` | 顶栏 **CAN 弹窗** + `cabana_analyze` |
| — | `get_vehicle_state` 读已有 fingerprint |

### 分析 — 五类必找 CAN

用 `analyze_can_id_pattern`，逐类确认：

1. 车速（如 `WHL_SPD_FL`）  
2. 转向角（`STEER_ANGLE` / `SAS_Angle`）  
3. 制动  
4. 油门踏板  
5. 档位  

输出 `FINGERPRINTS = {'MODEL': [{0x50: 8, 0x140: 8, ...}]}` 候选 → `save_adaptation_draft`，**禁止**直接改 `opendbc/car/fingerprints.py`。

**固件指纹（FW）**：路线含 `carParams` 时，优先 `car_porting_auto_fingerprint`（等同 `tools/car_porting/auto_fingerprint.py`）；可 `car_porting_fingerprint_to_draft` 写入 `adaptation_drafts/`。PC 开发机再合入 `opendbc/car/fw_versions.py`。

工具链：`list_dbcs` → `read_dbc_file` → `analyze_can_id_pattern` → `car_porting_auto_fingerprint`

---

## 2. CarState

草稿须含：`vEgo`, `steeringAngleDeg`, `gas`, `brake`, `gasPressed`, `brakePressed`, `standstill`, `gearShifter`（若有）。

`cabana_explain_signal` 对照 DBC；`get_full_vehicle_state` 验证与实车一致。

---

## 3. CarController

典型：`LKAS11`（`STEER_TORQUE`, `STEER_REQ`）、`SCC12`（`ACC_REQ`, `ACC_ACCEL`）。

草稿注明：`apply_driver_steer_torque_limits`、高速 `MAX_STEER_SPEED` 清零转向、`STEER_DELTA_UP/DOWN`。

`save_adaptation_draft` → `export_adaptation_bundle` → PC 合入 opendbc。

---

## 4. 车型与控制参数

`CarSpecs(mass, wheelbase, steerRatio)`、`STEER_MAX`、`ACCEL_MIN/MAX` 写在 `values.py`。

用户**行驶调优**用 `dp_*`（**dp-tuning** 技能），与此处代码适配不同。

---

## 5. 调试

| 开发机 | 车机 |
|--------|------|
| `cereal dump carState/carControl` | `get_vehicle_state` / `get_full_vehicle_state` |
| PlotJuggler | `trip_review` + PC 看 route |
| 日志 tail/grep | `grep_log`, `grep_log_errors`, `read_manager_log` |
| Params CLI | `read_params` |

---

## 6. 安全验证（封闭场地）

转向：角度反馈、扭矩限制、故障断开。  
纵向：加速度、制动、跟车。  
静止时可用 `car_porting_test_route`（等同 `tools/car_porting/test_car_model.py`）对路线跑 `TestCarModel` 回归。  
AI 只出清单；人执行。路试前 `read_onroad_events` 无致命项。

---

## 7. 故障排除

**无法识别**：指纹五类 CAN、harness/panda、DBC、SecOC 密钥 → **engage-troubleshooting**

**控制不响应**：LKAS/SCC 报文格式、STEER 限幅、CarState 与 CAN 是否一致

---

## 工具链（汇总）

`get_vehicle_state` → `read_params` → `search_knowledge_base`  
→ `list_dbcs` → `read_dbc_file` → `suggest_signals_for_adaptation`  
→ Cabana / `extract_can_ids_from_route` → `analyze_can_id_pattern` → `compare_fingerprint`  
→ `car_porting_auto_fingerprint` / `car_porting_test_route` / `car_porting_test_interfaces`  
→ `search_local_routes_for_can` / `car_porting_search_segments_by_can` / `search_car_segments`  
→ `get_adaptation_template` → `save_adaptation_draft` → `export_adaptation_bundle`（Web 下载 `/api/ai/adaptation/{id}/bundle?download=1`）

静止时可 `run_shell`: `list_adaptation_drafts`, `grep_log_errors`

## 禁止

- 写入 `opendbc/` 生产路径  
- 代写 `SecOCKey`  
- 公开道路首次控车  

从 CP fork 迁移调参名见 **carrot-legacy** 技能。
