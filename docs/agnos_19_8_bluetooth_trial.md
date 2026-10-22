# AGNOS 19.8 原生蓝牙 / Cinque v3 试验文档

> 来源：https://github.com/ajouatom/openpilot/blob/d4fca67f20bc18ea543d93f9db5a7ac4fef66f91/docs/agnos_19_8_bluetooth_trial.md
> 分支：carrot-cinque_v3，commit d4fca67f20bc18ea543d93f9db5a7ac4fef66f91
> 日期：2026-09-17

---

## 概述

在 Cinque v3 设备上集成 AGNOS 19.8 原生蓝牙支持的实验记录。增加了 WCN3990 射频、BlueZ、经典 HID、BLE HID、RFCOMM 和配对加密功能。

新镜像名称：`19.8-carrot-bt1`

---

## 范围

- 用户于 2026-09-17 在 `carrot-cinque_v3` 分支上请求进行此组合实验
- 保留现有的 Carrot USB-PD v3 补丁、C3 特定 PCIe/NVMe 补丁、传统 C3 启动固件清单和 Carrot 的 Adreno 库选择
- 蓝牙支持由两个设备启动镜像共享
- 实际硬件验证从 C4 开始

---

## AGNOS 审核

- openpilot commit `cab53438` 选择 AGNOS 19.8
- AGNOS 构建器 `bdbf1bc` 是 19.8 发布源
- 蓝牙内核更改和启动序列选自 StarPilot
- 归属和确切源哈希记录在构建器的 `patches/BLUETOOTH.md` 中

---

## 模型接口和 tinygrad 审核

- 固定的 v3 模型仍使用上游 PR #38932 提交 `892fc3a1`
- SHA-256: `e758b96df27858ea97122d18554930d04f9f8bda417417074edfb3a72b008d0b`
- 内部驾驶和驾驶员监控模型保持不变

---

## 蓝牙试用操作

### 启用蓝牙

```sh
sudo install -d -m 700 /data/bluetooth
sudo touch /data/bluetooth/ENABLED
sudo systemctl start carrot-bluetooth-radio
bluetoothctl show
bluetoothctl --timeout 15 scan on
```

### 禁用蓝牙

```sh
sudo rm -f /data/bluetooth/ENABLED
sudo systemctl stop carrot-bluetooth-radio
```

---

## 硬件验证结果

| 测试项目 | 结果 |
|---------|------|
| `/dev/btpower`、`ttyHS1` (蓝牙) 和 `ttyHS0` (GPS) 存在 | ✅ |
| 原生 `hci0` 正常启动，报告 BR/EDR、LE 和安全连接支持 | ✅ |
| 10秒观察收到 201 帧连续帧，无帧丢失，中位模型执行时间 39.28 ms | ✅ |
| 固件从活动蓝牙分区只读挂载，`/var/lib/bluetooth` 由 `/data/bluetooth` 支持 | ✅ |
| 带启用标志重启后自动启动无线电 | ✅ |

---

## Yiser-J6 遥控器按钮映射

### 原始 HID 报告

| 按钮 | 观察到的输入 |
|------|-------------|
| 上 | 触摸滑动，ABS_Y 增加 |
| 下 | 触摸滑动，ABS_Y 减少 |
| 左 | 触摸滑动，ABS_X 增加 |
| 右 | 触摸滑动，ABS_X 减少 |
| 中心 | 触摸点击 at (300, 500) |
| 1 | `KEY_VOLUMEUP` (115)，按下并释放 |
| 2 | 触摸点击 at (420, 850) |

### 默认 Carrot 操作映射

| Yiser-J6 按钮 | 默认 Carrot 操作 |
|--------------|-----------------|
| 上 | `accelCruise` |
| 下 | `decelCruise` |
| 左/右 | 现有遥控器车道变更请求，左/右 |
| 中心 | 踏板减速 |
| 1 | 循环巡航跟车距离 |
| 2 | 无操作 |

---

## Carrot Web 映射功能

- 工具 → 蓝牙遥控器提供射频控制、30秒发现、显式设备配对、连接/断开/忘记
- 每设备输入配置文件和操作映射
- 设置需要新鲜静止、脱离遥测或确认离路状态
- HTTP API 无法执行车辆操作
- 配对是应用范围的
- `carrot_bluetooth` 独立于 Web 服务器运行
- 映射存储在 `/data/carrot/bluetooth.json`

---

## 多遥控器、点击手势和 CarrotCruise

### 功能特性

- 支持每按钮短按、双击和长按操作
- 双击使用 350ms 释放到释放窗口
- 长按在 700ms 后触发，持续按住时每 500ms 重复加速/减速
- 设备特定解码器防止两个遥控器合并为一个双击
- 支持最多 16 个设备
- `carrotCruise` 进入现有 `carrot_cruise_active` 模式

---

## 原生长按按钮操作

| 原生操作 | 结果 |
|---------|------|
| `accelCruiseLong` / `decelCruiseLong` | 一个现有的 10 单位速度步长；禁用时可请求接合 |
| `gapAdjustCruiseLong` | 现有驾驶模式循环 |
| `lfaButtonLong` | 现有车道线模式切换 |
| `cancelLong` | 巡航取消和横向禁用 |

---

## 长按保持动作

- 分配的 `@long` 手势在 700ms 时触发
- 速度操作 `accelCruise`、`decelCruise`、`accelCruiseLong` 和 `decelCruiseLong` 每 500ms 重复一次
- 其他动作每保持只执行一次
- 释放、输入丢失、触摸方向改变、映射/测试转换和 10 秒超时停止重复
- 踏板、物理车辆按钮、离开 D 档、无效车辆状态和巡航脱离取消保持

---

## 回滚说明

1. 停止 comma 服务
2. 恢复匹配的上一个 openpilot OS 清单/版本
3. 使用 `sudo abctl --set_active 1` 选择保留的 B 槽
4. 重启

---

## 原始镜像 SHA-256 值

- C3 启动: `9d1c81ef890edf349e0919260a850ab5d1f95162fbd4b262cfcd52d92c0ac0b8`
- C3X/C4 启动: `dccd7965346b0a87a9f64cb6be257f6bb5d3d0f368c8655085efc1e460527f5a`
- 通用系统: `375c5d22335770ac08750660bb5b29a3331c550d6a9875b35f36b88af792ea44`

---

## 验证测试结果

| 测试类别 | 通过数量 |
|---------|---------|
| 模型/工件/运行器测试 | 57 |
| 映射相关测试 | 75 |
| 多遥控器/CarrotCruise 测试 | 94 |
| 原生按钮/接合测试 | 140 |
| 长按保持测试 | 160 |
| Web 测试 | 14 |

---

## 设备上的证据文件

- `/data/carrot-bluetooth-trial/before.json`
- `/data/carrot-bluetooth-trial/staged.json`
- `/data/carrot-bluetooth-observation-after.json`
- `/data/carrot-bluetooth-model-after.json`
- `/data/carrot-bluetooth-yiser-keys.log`
- `/data/carrot-bluetooth-mapping-events.json`

---

**注意**: 这是一个开发者专用的 OS/模型兼容性实验，没有添加用户面向的设置或更改设置行为。
