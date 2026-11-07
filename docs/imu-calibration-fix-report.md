# IMU 自动校准 — 缺陷分析与修复报告（2026-09-30）

> 问题：IMU 自动校准打开后上路行驶会不会报错？
> 结论：**会，而且是从第一步就 100% 失败**。已定位 3 个真实缺陷并修复。
> 遗留 1 个设计级问题需决策。

---

## 一、缺陷清单（全部有代码级证据）

### 🔴 D1：静态阶段坡度判据用反方向 —— 校准永远无法启动

**位置**：`imu_calibrationd.py::compute_static_rotation`

```python
cos_angle = float(np.dot(up_device, VEHICLE_GRAVITY))   # ❌
slope = math.acos(...); if slope > STATIC_MAX_SLOPE_ANGLE: raise SlopeTooSteepError
```

- `up_device` = 加速度计比力方向 = **vehicle UP**（注释也这么写）
- `VEHICLE_GRAVITY = [0,0,-1]` = **重力方向**（向下）
- 二者恒为反平行 → `cos = -1` → `acos(-1) = 180°` → **必然抛 `SlopeTooSteepError`**

**影响**：`finish_static()` 100% 失败 → 状态机永远进不了动态阶段。
**实测**：`compute_static_rotation([[0,0,1]]*100, ...)` 直接抛
`SlopeTooSteepError: ground slope too steep: 180.0 deg`

**修复**：改用 `VEHICLE_UP` 并取绝对值（兼容 C3 正装/倒装两种合法安装）。

---

### 🔴 D2：yaw 解算投影数学错误 —— 动态阶段恒失败

**位置**：`imu_calibrationd.py::compute_yaw_correction`

原代码把**旋转向量**（轴角）当作普通矢量做垂直投影，再读 `atan2(v[1], v[0])`：

```python
pred_xy = pred_rot - np.dot(pred_rot, z_axis) * z_axis   # ❌
pred_angle = math.atan2(pred_xy[1], pred_xy[0])          # ❌ 假设 z_axis == [0,0,1]
```

两个子问题：
1. **当运动绕重力轴时**，旋转向量平行于 `z_axis`，垂直投影**恒为零** → 每个区间都被 `if p_norm < 1e-6: continue` 跳过 → `diffs` 永远为空 → 抛 `insufficient dynamic samples: 0`。
2. **`atan2(v[1], v[0])` 隐含假设 `z_axis == [0,0,1]`**。本功能存在的意义正是「设备任意角度安装」，此时 `z_axis` 是任意方向，直接读 x/y 分量**没有物理意义**。

**数学推导**（已验证）：
- 待求的 yaw 是绕重力轴的旋转 ψ
- 旋转向量沿重力轴的分量 `<Rz(ψ)v, z> = <v, z>` **不变**，不携带 ψ 信息
- 携带 ψ 信息的是旋转向量**在垂直平面内的方位角**

**修复**：构造垂直于重力的正交基 `(u_axis, w_axis)`，在基内取方位角比较：

```python
u_axis = normalize(cross(z_axis, [0,0,1]))   # 退化时换 [0,1,0]
w_axis = cross(z_axis, u_axis)
pred_angle = atan2(dot(pred_rot, w_axis), dot(pred_rot, u_axis))
meas_angle = atan2(dot(meas_rot, w_axis), dot(meas_rot, u_axis))
diffs.append(meas_angle - pred_angle)
```

**验证**：4 种安装姿态 × 3 种 yaw 偏差 = **12/12 全部解算正确**（误差 0.15°，为构造数据采样偏置）：

| 姿态 | 真值 10° | 真值 -30° | 真值 120° |
|---|---|---|---|
| C3 倒装 | 10.15 ✅ | -29.85 ✅ | 120.15 ✅ |
| 正装 | 10.15 ✅ | -29.85 ✅ | 120.15 ✅ |
| 倾斜 30° | 10.15 ✅ | -29.85 ✅ | 120.15 ✅ |
| 横置 | 10.15 ✅ | -29.85 ✅ | 120.15 ✅ |

**端到端**：静止 → 直线行驶 → **4.6s 完成**，yaw 误差 1.29°，矩阵 det=1.0000。

---

### 🔴 D3：`helpers.py` 重复方法 —— 粘滞保护完全失效

**位置**：`locationd/helpers.py`

`feed_extrinsics_calibration` 被**定义了两次**（L171 与 L210），Python 中后者覆盖前者：

- **L171 版本**（设计意图）：带 `_imu_source_seen` 粘滞保护 —— IMU 校准一旦出现，相机标定帧不得再覆盖，否则各消费方（paramsd/controlsd/torqued/lagd）的位姿变换会在两种来源间反复横跳，导致 **paramsd 发散 / "paramsd 临时错误"**
- **L210 版本**（实际生效）：无任何保护，相机帧会直接覆盖 IMU 矩阵

**影响**：精心设计的保护逻辑**从未生效**。
**修复**：删除 L210 的重复定义。

---

## 二、附带改进

### 放宽 `DYNAMIC_MAX_YAW_RATE`（0.10 → 0.25 rad/s）

原阈值 5.7°/s 过严，实际可达性分析：

| 场景(60km/h) | yaw_rate | 原阈值 | 新阈值 |
|---|---|---|---|
| 直路 | 0°/s | ✅ | ✅ |
| 缓弯 R=500m | 1.9°/s | ✅ | ✅ |
| 缓弯 R=300m | 3.2°/s | ✅ | ✅ |
| 中弯 R=200m | 4.8°/s | ❌ | 由横向加速度拒绝（1.39>1.0） |
| 急弯 R=80m | 11.9°/s | ❌ | ❌ |

- 原阈值下 60km/h 曲率半径 <167m 的**正常弯道都被拒绝**，用户极易撞上 `DYNAMIC_TIMEOUT = 300s`
- 新阈值让高速缓弯可通过；急弯仍由**横向加速度门**（物理意义的判据）正确拒绝
- **安全性未降低**（实测 12 组弯道全部按预期判定）

---

## 三、坡度检查的处理（已按方案 D 决策）

### 问题本质

测试语义自相矛盾：

| 测试 | 构造 | 期望 |
|---|---|---|
| `pure_roll` | `rot_from_euler([-20°,0,0])[:,2]` | **成功** |
| `slope_too_steep` | `rot_from_euler([+8°,0,0])[:,2]` | **拒绝** |

两者输入结构**完全相同**（都是 `rot_from_euler([角度,0,0])` 取第三列），仅角度不同，却要求相反结果。

**根本原因**：静止时 IMU 只能测到「vehicle up 在 device frame 的方向」。它**无法区分**「设备倾斜安装 20°」与「地面有坡度 20°」——数学上不可分。因此该检查**不可能是真正的坡度检测**。

### 决策：方案 D — 保留检查但重新定义语义

**用户决策（2026-09-30）：保持现状（保留检查）+ 阈值放宽到 45°**

实现：

```python
STATIC_MAX_SLOPE_ANGLE = math.radians(45.0)

cos_angle = abs(float(np.dot(up_device, VEHICLE_UP)))
slope = math.acos(max(-1.0, min(1.0, cos_angle)))
if slope > STATIC_MAX_SLOPE_ANGLE:
  raise SlopeTooSteepError(f"device is not vertical: {degrees(slope):.1f} deg from vertical")
```

- **语义重新定义**：不再是「地面坡度」检测，而是「设备是否近似竖直」的**合理性前置校验**
- **`abs()`**：兼容 C3 正装（0°）与倒装（180°）两种合法安装
- **45° 阈值**：允许倾斜支架安装，只拒绝明显异常姿态
- **真正的保护**：由 `_validate_final_matrix` 的 `MATRIX_MAX_ROLL_PITCH_DIFF`（5°）在**结果侧**兜底

实测行为：

| 场景 | 结果 |
|---|---|
| 0° 正装 | ✅ 通过 |
| 180° 倒装（C3 常见） | ✅ 通过 |
| ±20° / 30° 倾斜支架 | ✅ 通过 |
| 44°（接近阈值） | ✅ 通过 |
| 50° / 90° 横置（异常） | ✅ 正确拒绝 |

---

## 四、测试现状与更新

设备端 `test_imu_calibrationd.py` 原有 **22 个用例、失败 9 个**（8 errors + 1 failure），**从未通过**——它们是照着一个有问题的预期写的。

### 修复的测试问题（三类）

| 类别 | 具体问题 | 处理 |
|---|---|---|
| **断言过严** | `compute_static_rotation` 返回的 R 只是 pitch/roll 解，yaw 按约定为 0，但测试断言整个矩阵等于 `R_true`（含 yaw） | 改为只断言重力轴 `R[:,2]` |
| **约定不一致** | 测试用 `rot_from_euler([0,0,ψ])`（绕 **+Z**），而代码的 `z_axis = R_static @ VEHICLE_GRAVITY = [0,0,-1]`（绕 **-Z**），二者互逆 → 解出的 yaw 符号相反 | 改用 `axis_angle_to_rot(z_axis, ψ)` 构造真值；欧拉读取处改比矩阵 |
| **时间戳陷阱** | 多个测试设 `dynamic_start_ts = 0.0`，而 `update()` 用真实 `time.monotonic()` 判断超时 → `now - 0 = 巨大值 > 300` → **立即超时** | 改为 `time.monotonic()` |
| **capnp 类型** | numpy 标量不能赋给 capnp 字段（`KjException: unsupported type numpy.float64`） | `_device_to_sensor_msg_frame` 强制转 `float` |

### 新增回归用例（3 个）

1. `test_compute_yaw_correction_arbitrary_mount` —— **D2 的回归**，覆盖 3 种非 Z 轴重力方向的安装姿态
2. `test_compute_static_rotation_rejects_non_vertical_device` / `test_compute_static_rotation_accepts_tilted_mount` —— 坡度语义拆分为「拒绝异常」+「接受倾斜」
3. `test_calibrator_static_phase_accepts_tilted_mount` —— 倾斜安装可正常进入动态阶段

### 结果

| | 修复前 | 修复后 |
|---|---|---|
| 用例数 | 22 | **25** |
| 通过 | 13 | **25** |
| 失败 | 9（8 err + 1 fail） | **0** |
| 设备端 | — | ✅ `Ran 25 tests ... OK` |

---

## 五、修复文件清单

| 文件 | 改动 |
|---|---|
| `openpilot/selfdrive/locationd/imu_calibrationd.py` | D1 坡度判据（`VEHICLE_UP` + abs + 45°）+ D2 yaw 正交基解算 + `DYNAMIC_MAX_YAW_RATE` 0.10→0.25 |
| `openpilot/selfdrive/locationd/helpers.py` | D3 删除重复方法（-13 行） |
| `openpilot/selfdrive/locationd/test/test_imu_calibrationd.py` | 同步预期 + 3 个回归用例（+187/-66 行） |

**提交**：`df61c8fd9` — 已 push `origin/test`，设备已同步验证。

**验证状态**：
- ✅ 本地编译通过
- ✅ yaw 解算 12/12 姿态组合正确（修复前 0/12）
- ✅ 端到端 4.6s 完成（修复前必然失败）
- ✅ 设备端 25/25 单测通过
- ✅ 设备端代码 = 仓库版本（`df61c8fd9`）

---

*报告时间：2026-09-30；所有结论均有文件路径级代码证据与实机测试结果。*

