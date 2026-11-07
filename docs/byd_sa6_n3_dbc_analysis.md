# BYD SA6（N3 平台）DBC V2.8.0 与 opendbc BYD 端口比对分析

来源：`C:\Users\mouxan\Downloads\BYD_SA6_原始DBC_11份`（IDCC-B10 SA6 OTA 包提取，V2.8.0 20251225，11 份 CAN FD 平台化矩阵，cantools strict=True 全部通过）。
比对对象：`opendbc/dbc/byd_generic_pt.dbc` + `opendbc/car/byd/`（28 平台 CID_* 端口）与 `byd_general.dbc`（ATTO3）。

## 1. 总体判断

SA6 = 王朝网 N3A1 硬件（vehicle_dbc.csv 第 72 行，0x14A1，power_type=3 纯电/混动共用），CAN FD（BRS，64 字节报文），真实 ECU 命名（EPS/VCU/IPB/CCU/ADC/MRR/SWS/SCU）。这是**新一代平台架构**，与现有端口的混淆 CID_* 经典 CAN 体系是两代东西：

- 不存在"抄错因子/位偏"之类的纠错项——SA6 矩阵不能反过来证明现有老平台 DBC 有错。
- 但同 ID 报文显示 0x1E2/0x32E/0x32D/0x316/0x1FC/0x3B0 是**同一指令契约的演进版**，说明 ADAS→执行器的消息架构是延续的，接入 N3 主要是加新 port 而非改协议。

## 2. 同 ID 血缘比对（逐报文）

### 0x1E2 角度控制指令（我们 CID_TCDUBH / SA6 ADC_0x1E2，8B @20ms）
| 信号 | 我们 | SA6 | 结论 |
|---|---|---|---|
| 扭矩上限 x0.01 0-5 | sig_hfquge @0 len10 | MotorTorqueUpperLimit_S @0 len10 | 一致 |
| 扭矩下限 x0.01 -5-0 | sig_tqntde @10 len10 | MotorTorqueLowerLimit_S @10 len10 | 一致 |
| 状态 | hfhxif @20 len1 + ausukb @21 len1（两个 1bit） | ADC_AngleReq_St_S @20 len2（2bit 枚举） | 兼容：St=(ausukb<<1)\|hfhxif；我们 active 写 1/0 → St=2 |
| ADC2SCU_P_Req | sig_uipsvp @22 len2 | ADC2SCU_P_Req @22 len2 | 一致 |
| 角度请求 x0.1 ±780 | sig_kqgoqc @24 len16 | ADC_AngleReq_S @24 len16 | 一致 |
| 精度/保留 | sig_yjvxpi @47 len8 BI | ADC_PrecisionRequest @40 len8 LE | 位置/位序变了（我们不写，模板透传，无影响） |
| Counter/Checksum | @52 len4 / @56 len8 | @52 / @56 | 一致 |

### 0x32E ACC 纵向指令（我们 CID_RJDCMR / SA6 ADC_0x32E）
| 信号 | 我们 | SA6 | 结论 |
|---|---|---|---|
| 目标加速度 | sig_zspfbe x0.05 **-5** (-5..2.75) | ACC_Axv_Cv_Aim x0.05 **-7** (-7..5.75) | offset 变了，量程扩大 |
| 加速度带上下限 | umvvum/ffvcas x0.05 **-5** | Axv_Cv_Coft_Band_U/L x0.05 **-7** | 同上 |
| jerk 上/下 x0.2 | sig_vfmqcq @24 / sig_vuisck @32 | ADt_Upper @24 / Adt_Lower @32 | 一致 |
| rfss/sss/minbrake | @39 / @40 / @41 | ACC_Drive_Off @39 / DecTo_Stop @40 / Min_Braking @41 | 一致 |
| **ACC_Mode** | sig_gbaqki @45 len3 **BI** | ACC_Mode_S @43 len3 **LE** | **位置+位序都变了**，这是 N3 与老平台最实质的指令差异 |
| Counter/Checksum | @48 / @56 | @48 / @56 | 一致 |

### 0x32D ACC HUD（我们 CID_XQYNBW / SA6 ADC_0x32D）
Set_Speed @0 len9、Tau_Gap_Set @10 len3、Dx_Tar_Obj @13、ACC_Mode_Display @19 len3（=我们 sig_hprcqm 同位同长）、ACC_State @22、Take_Over_Req @23、Counter/Checksum @52/@56 —— HUD 解析契约一致。我们的 cruiseState.enabled 判定（acc_state in (3,5)）与 ACC_Mode_Display 枚举需在 N3 上重新核对值表。

### 0x316 LKA 指令（我们 CID_HGZKCQ / SA6 ADC_0x316）
同为 bit16 len11 扭矩槽位，但 SA6 明确 **Output_LKS_torque_request x0.01 ±10.23Nm**（我们是原始计数）。另有 Lane_Assistant_Mode @6、TJA_ICA_function_status @36、LKS_torque_request_staus @27（=我们 sig_ausukb 同位 len2 vs len1 微差）。

### 0x1FC EPS 扭矩（我们 CID_KERMHK / SA6 EPS_0x1FC）
SA6 只剩 StrngWhlTorq_S x0.01 ±12.5Nm @4 len12（=我们 sig_bhnetn 同位，但明确 0.01 因子）；状态/角度字段移去了 EPS_0x06D。

### 0x3B0 方向盘按键（我们 CID_YHMGPU / SA6 SWS_0x3B0）
同 ID，键位重排，且 SA6 给了完整 VAL 枚举：
- SWS_Speed_Set：0=初始、1/2=减速两档、3/4=加速两档（对应我们 setCruise/decelCruise/accelCruise 映射）
- SWS_Dist_Set：1s/1.5s/1.9s/2.3s 四档跟车距离
- Dipilot_Switch_Signal：1=按下

## 3. 新平台的传感器链路（N3 独有，质量高于现端口）

| 功能 | SA6 报文 | 说明 |
|---|---|---|
| 四轮车速 @10ms | IPB_0x10C (Control) | x0.06875 km/h + 方向 + pulse counter + standstill；CCU_0x0FC (Chassis) 重复一份含 Veh_spd+SAS 角 |
| 转向 @10ms 64B | EPS_0x06D | 小齿轮角/方向盘角+角速率（各带 Vld）、司机扭矩 x0.02 ±20Nm、DrvrOvrd 位、SteerMod |
| 油门 | VCU_0x05A Act_acce_pedl_perc 0-100% | + VCU_0x342 油门/刹车 % |
| 挡位 | VCU_0x342 Goal_Gear（P=1 R=2 N=3 D=4）/ SCU_0x35C | 带完整枚举 |
| IMU | CCU_0x10B @10ms（xyz 加速度+角速度）+ IMU 子网 SRS_0x02C @2ms（g 值） | 现端口没有等效源 |
| 雷达目标列表 | MRR_0x640-0x66E 64B | Conti ARS 风格：8 目标/报文，range x0.0625m、vrad x0.1-120、方位 x0.002rad、RCS/SNR/DynProp/Quality，0x66E 带目标数、0x66F 传感器状态 |
| ADAS 主转向请求 64B | ADC_0x057 @10ms | 角度请求(±720°)+扭矩请求(±20Nm)+纵向上/下扭矩+AEB 扭矩+yaw 扭矩合一（0x1E2 是它的 8B 兼容版） |

车速链路用真实轮速后，现有 generic 端口的 `K_DASHSPEED=0.0719088` 仪表换算 + SpeedCorrect30/60/90/120 参数修正 hack 在 N3 上不再需要。

## 4. 需要的调整（按优先级）

### A. 现有 28 平台：不改代码，但有一个验证点
SA6 不构成对老平台 DBC 的纠错。**唯一实质风险点**：PLATFORM_SEAL/TENGSHI/QIN_SEAL06（0x1E2 角度控制 + 0x32E ACC 改写）里如果混有 N3 代际实车（2024-2025 款部分车型可能已切新矩阵），我们的 0x32E `sig_gbaqki` 写 bit45 BI（bits 44-46）会落错位——N3 的 ACC_Mode 在 bits 43-45 LE，且 bit46 是 ESP_VLC_ShutDown。若这些车出现 ACC 接管异常，首先核对 0x32E bit43-46 实测。0x1E2 因模板透传 + St 字段组合兼容，风险低。

### B. 接入 N3 平台（新增 port）工作清单
1. **DBC**：从 11 份中裁剪出 `byd_n3_pt.dbc`（Control+Chassis 关键报文子集，经典帧转换需实车确认是否 BRS）
2. **values.py**：新增 platform + BydFlags（CANFD 必须置位）+ CarSpecs（N3A1 对应车型的 wheelbase/steerRatio）
3. **carstate.py**：IPB_0x10C 轮速（免 dashspeed 修正）、EPS_0x06D 角度/扭矩、VCU_0x342/SCU_0x35C 挡位、SWS_0x3B0 按键（用 VAL 枚举）
4. **carcontroller.py**：ACC 走 0x32E 新布局（offset -7、Mode@43 LE）；角度控制优先验证 0x1E2 checksum 算法是否仍为 0xAF 半字节折叠（DBC 未记录算法，须实车抓包）
5. **radar_interface.py**：新增 MRR_0x640 系列完整目标列表解析（替代 CID_NCBHOL 单目标，信息量质变）
6. **panda safety**：新消息布局校验（Mode@43、扭矩限幅域、BRS 帧）
7. **指纹/fw**：0x14A1 = SA6；待实车 UDS 响应确定 ECU 清单

### C. 校验和算法
DBC 只写"校验和"注释（GBK 乱码），无算法描述。Counter@52/Checksum@56 位置与我们一致，大概率延续同族算法，但 0xAF 定 key 是否变化必须实车验证后才能发包。

## 5. 本次比对的价值小结

1. **验证**了现有角度控制/ACC/HUD 指令契约在 BYD 新平台上是延续的（同 ID、核心布局同源）——现有端口架构方向正确。
2. **预警**了 0x32E ACC_Mode 位移这一实质差异（N3 车型若混入现有平台组，这是第一排查点）。
3. **铺好**了 N3 平台接入的完整信号地图（车速/转向/踏板/挡位/IMU/雷达全部有干净来源），待实车日志即可开工。

## 6. 实现状态（2026-11-03 更新：v1 已落地）

opendbc 侧 N3 平台 v1 已实现并推送（opendbc 仓 `0f8ee3b9f`）：

- `opendbc/dbc/byd_n3_pt.dbc`：19 报文子集（原文提取，VAL_ 枚举保留）
- `values.py`：`BYD_SA6_N3` 平台 + `PLATFORM_N3` + `BydSafetyFlags.N3=0x800`（wheelbase/steerRatio 占位）
- `carstate.py`：`_update_n3`（真实轮速免 dashspeed 修正 / EPS 物理扭矩 / VCU 踏板+挡位枚举 / SWS 按键 / ACC_Mode_Display 状态）
- `bydcan.py`+`carcontroller.py`：`n3_angle_control`（0x1E2，AngleReq_St 2bit）+ `n3_acc_cmd`（0x32E 新布局）
- `radar_interface.py`：MRR 0x640-0x647 目标簇列表解析（8 目标/帧，0x66E 计数）
- `interface.py`：N3 分支（角度控制 / pcmCruise / MRR 雷达）
- `safety/modes/byd.h`：N3 平台（rx 位精确提取 / tx 角度校验 / fwd 接管超时 / counter 校验：0x1E2+0x32D @52、0x32E @48；checksum 校验暂关待实车验证 0xAF 算法）

**PC 已验证**：cantools strict 解析、CANParser 构造、carstate 空数据 update、控制器构造、0x1E2/0x32E 字节级 packer round-trip（角度/扭矩限幅/ACC offset -7/Counter/Checksum 逐位核对）。
**待实车**：scons 编译 + safety 测试 + test_car_interfaces（依赖 libparams/safety 原生库）、0xAF checksum 算法确认、真实指纹（fingerprints.py 暂无条目）、wheelbase/steerRatio 实测、CAN FD 总线拓扑确认（当前假设 bus0=车控/底盘、bus2=ADAS 域）。
