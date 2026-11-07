# 双 panda（内置 dos + 外接 USB 红熊）CAN 模式

本文档描述 openpilot 对"一只 panda 跑 CAN/safety + 第二只 panda 同时上线"的支持，
即 **dual-panda CAN 模式**（区别于旧的互斥切换 / aux-仅风扇模式）。

## 总线约定（全品牌通用，一劳永逸的核心）

```
panda0（活动 panda，safety + 控制输出）  → 逻辑 bus 0-2（摄像头/控制段）
panda1（辅助 panda，如内置 dos）         → 逻辑 bus 4-6（OBD/动力段，本地 bus b = 逻辑 4+b）
```

- 偏移量本身不是逐车知识：pandad 做机械的 `src + 4×panda_index`（RX）与
  bus 段路由（TX），品牌代码不感知。
- 真正的逐车知识只有"拓扑"（哪个 ECU 在哪一段），写在各品牌
  `CanBus(CanBusBase)` 类里。`CanBusBase.offset = 4 × (len(CP.safetyConfigs) − 1)`
  自动给出偏移。
- **safety C 固件零改动**：每只 panda 的固件 safety 只见自己本地 bus 0-2。

## pandad 行为（openpilot/selfdrive/pandad）

| 阶段 | RX（辅助 panda） | TX（辅助 panda） |
|---|---|---|
| 指纹期（ELM327） | src 原样透传（0-2）——保证 UDS 响应与查询 bus 匹配 | 镜像主 panda 的 0-2（动力段 ECU 才能收到查询） |
| safety 配置后 | src + 4（=逻辑 4-6） | 只收 4-6（发到本地 bus = src−4） |

- `pandaStates` 按在线 CAN panda 数量发布；`safetyConfigs[i]` 下发给第 i 只
  panda（selfdrived / card / xiaoge_startup 均按此 per-index 语义校验）。
- `car_helpers.get_car` 在 `num_pandas > 1` 时把 `safetyConfigs[0]` 复制一份，
  由此激活 `CanBusBase.offset`。
- 辅助 panda 断线不拖垮主 panda：aux 收发线程各自退出，主链路继续。

## 使用方法

前置：`UseRedPanda = 1`（红熊为活动 panda），内置 dos 在线（aux 槽）。

```bash
# 开启双 panda CAN 模式（默认关闭 = 原 aux-仅风扇行为）
echo -n 1 > /data/params/DualPanda
sudo reboot
```

接线约定：红熊接摄像头段（相机 ECU 所在线束），内置 dos 接 OBD/动力段。

## 品牌支持状态（CanBusBase 迁移）

| 状态 | 品牌 | 说明 |
|---|---|---|
| 已迁移 | toyota / honda / ford / volkswagen / hyundai(CANFD) / **byd** / **gm** / **subaru** | 双 panda 下自动偏移 |
| 未迁移 | hyundai 经典 / mazda / nissan / chrysler / tesla / rivian / psa / mg | 裸 bus 字面量，双 panda 下视作"仅主 panda"（等同单 panda 行为，功能降级不危险） |

约定门禁：`opendbc/car/tests/test_canbus_convention.py` —— 任何新定义的
`class CanBus` 必须继承 `CanBusBase`，否则 CI 失败。新增车型端口请照
`opendbc/car/byd/values.py::CanBus` 的写法声明拓扑。

品牌内拓扑默认值（如与实际接线不符，改品牌 CanBus 一行即可）：
- 车侧/动力侧总线（动力、雷达等）→ `offset`/`offset+1`（辅助 panda）
- 摄像头 ECU → 恒 `2`（主 panda）

## 已知限制

- dos（F4/bxCAN）只有经典 CAN，CAN FD 车型（如 BYD N3）动力段嗅探不可用。
- Toyota `alt`（雷达）默认映射到辅助 panda；若实车雷达在主 panda 段，改
  `toyota/values.py::CanBus.alt` 一行。
- 未迁移品牌在双 panda 下丢失辅助段数据（指纹可能不完整）。
