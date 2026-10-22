# 导航 GPS 源选择收敛为单一判定 — 2026-10-20

## 问题

同一件事被算了两遍，而且结论不一致：

- `CarrotServ._phone_gps_is_usable()`（数据层）：要求 navi 已过期、phone 新鲜、
  `accuracy < 15 m`、坐标非零且在范围内。
- `CarrotServ.gps_source`（对外 UI / 诊断）：只看 navi/phone 各自是否 `< 3 s` 且坐标非零，
  **没有**精度门。

于是手机上报 `accuracy = 30 m` 时，数据层拒绝使用该定位，而 UI 仍报告 `phone`。另外两级
回退是硬编码的 `if navi ... elif phone`，没有第三级；两条外部源都断时，`vpPosPointPosLat/Lon`
保持 `(0, 0)`，路线曲率速度链（TurnSpeedControlMode 2/3）被静默降级。

## 改动

新增 `sunnypilot/carrot/gps_sources.py`（纯函数模块，无 Params / 无 messaging / 不自带时钟）：

- `Fix(lat, lon, heading, speed, accuracy, stamp)`：每个源各自带到达时刻。
- `plausible()`：经纬度范围、拒 `(0, 0)`、拒 `> 90 m/s`（GPS 速度）与非有限值。
- `fresh()` / `usable()`：按源各自的 `WINDOWS`（当前三者均 3 s），phone 额外要求
  `accuracy < 15 m`。
- `select()`：`PRIORITY = ('external_navi', 'phone', 'device')`，返回
  `('navi' | 'phone' | 'device' | 'none', Fix | None)`。

`CarrotServ` 改为：

- `_gps_fixes()` 组装三源快照；`update_raw` 的回退与 `gps_source` 属性都走 `select()`。
- 新增 `update_device_gps(sm)`：读 `liveLocationKalman`，门控条件与 mapd 一致
  （`status == valid`、`positionGeodetic.valid`、`gpsOK`），位置单位是度，**不声称精度**。
  由 `update_navi` 每帧调用；`carrot_man` 的 SubMaster 增加 `liveLocationKalman`。
- 设备源是最后一级：只在两条外部源都过期时填充，替代原来的 `(0, 0)`。

## 单位与刻意的保守选择

- 7706/7714 的 `nPosSpeed` / `gpsSpeed` **单位未确证**，因此不喂进 `Fix.speed`（传 0.0，
  恒满足合理性门）。只有设备源用 `cs.vEgo`（确定 m/s）。
- 设备源不带 heading（`heading=None` 表示不覆盖既有 `nPosAngle`），避免靠猜测从
  `velocityNED` 推航向。
- `liveLocationKalman.positionGeodetic.std` 与其 value 同量纲（度），所以不拿它跟 15 m 比。

## 验证

`openpilot/sunnypilot/carrot/tests/test_gps_sources.py`：21 例 —— 合理性（空岛、越界、
超速、非有限、零速）、逐源新鲜度边界与未来时间戳、navi 优先、phone 接替、粗精度被拒、
device 兜底、不可用源穿透、未知源忽略、公开标签稳定，以及 `CarrotServ` 侧的快照组装、
回退写 `_raw`、navi 优先、**UI 与数据层一致**、设备源可被报告、无效定位被忽略。

本机 15 例通过、6 例 skip（`CarrotServ` 需要 zstandard/opendbc）；车机
（`comma@192.168.7.233`，`c2df04b19`）21 例全部执行并通过，carrot 全套 610 例全绿。
另在车机上验证了 `messaging.SubMaster` 接受新的 12 服务列表（`liveLocationKalman` 名合法），
且 `carrot_man` 全程使用逐服务 `sm.valid/sm.alive`、没有无参 `all_checks()`，所以新增订阅不会
改变任何既有的可用性门控。

**未做**：隧道实测、与 llk 精度的对比数据、路线曲率链的实车回归。
