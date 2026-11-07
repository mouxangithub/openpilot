# 2026-10 评估：jetlink 链路承载 carrot HUD/导航数据

**结论：不实现。** carrot 已有更好的通道承载这些数据，jetlink HUD 通道的场景极窄。

## 需求背景

cp 的 jetlink 链路除模型推理外还承载 HUD/导航/WiFi 数据（`tools/jetlink/hud_protocol.py`
的 `carrot_hud_v1` capability，daemon 内嵌 modeld 直接发）。动机：cp 的外接主机走
USB gadget 单链路，模型与 HUD 共用一条连接。

## 为什么 sp 不需要

sp 的外接主机（Jetson/PC/Mac）通常**同时具备网络连接**（WiFi/以太网）。carrot 的
7000 端口 API 已经通过 WebSocket（`/ws/raw_multiplex`、`/ws/camera/*`）推送全部
HUD/导航/相机数据——navipilot 就是这么工作的。主机端直接订阅 7000，无需占用
jetlink 的推理链路。

**jetlink HUD 通道的唯一场景**：纯 USB gadget 连接、无网络的主机。该场景下主机
也无法收到任何 carrot 生态服务（导航、sunnylink），产品意义薄弱。

## 技术可行性（如果将来要做）

- v0.7.3 协议（`jetlink/protocol.py`）msg_type 1-18，10/11 已弃用，**空间可扩展**
- cp 在 v0.3 上的先例：自定义 msg_type 0x4000 + HELLO caps 里声明 `carrot_hud_v1`
- **障碍**：协议 VERSION=3，官方 server app（macos/ios/android）与车机端
  "updated together, each speaks exactly one version"。车机端加 msg_type 19+
  后，官方 app 对未知类型的容错未定义——破坏互操作风险
- 正确路径：向 jetlink 上游提案通用扩展通道，或在 sp 自己 fork 的 jetlink_repo
  上改（但 server 是官方 app，fork 包无法单方面生效）

## 放弃的替代方案

- 在 7000 WS 之外再开一个 HUD 专用 WS：7000 的 raw_multiplex 已覆盖，重复建设
- 让 webui 的流复用 jetlink transport：同一理由，且增加推理链路抖动风险
