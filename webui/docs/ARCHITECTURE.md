# WebUI 架构速览

> 详细对齐见 [GUI_ALIGNMENT.md](GUI_ALIGNMENT.md)、[GAP_VS_DEVICE.md](GAP_VS_DEVICE.md)

## 目录

| 路径 | 职责 |
|------|------|
| `webui/web/` | 静态资源（JS/CSS/图标）、`index.html` |
| `webui/server/` | aiohttp 路由、bridge、API |
| `webui/server/bridge/` | cereal → JSON state、model overlay |
| `webui/dev/` | PC mock（`WEBUI_DEV_PC=1`） |

## 数据流

```
cereal / Params → state_hub → /api/opui/state
modeld / mock   → model_overlay → /api/opui/model/overlay
摄像头          → WebRTC → <video>
前端            → WebGL lanes + DOM HUD
```

## 关键 API

| 端点 | 说明 |
|------|------|
| `GET /api/opui/state` | 行车/UI 状态 |
| `GET /api/opui/panels` | 16 个设置面板 schema |
| `GET /api/opui/model/overlay` | 模型 overlay（车道线 / 路径 / chevron） |
| `GET /api/opui/imu/calibration` | IMU 标定状态 |
| `POST /api/opui/imu/calibration/cancel` | 取消 IMU 标定 |
| `GET /api/opui/models/...` | 模型列表 / 选择 / 收藏 / 下载状态 |
| `POST /api/opui/webrtc/offer` | WebRTC SDP |
| `GET /api/opui/bootstrap` | 启动元数据（含 git short commit） |

## 安全与部署

- 车机启动后 HTTP `:5080` 会自动 302 跳转 HTTPS，用于 WebCodecs 与驾驶员相机预览。
- PC 预览（`WEBUI_DEV_PC=1`）保持 HTTP `127.0.0.1:5080`。

## 测试与交接

- PC：[TESTING_PC_DEVICE_SCRCPY.md](TESTING_PC_DEVICE_SCRCPY.md)
- 上车：[VEHICLE_QA_CHECKLIST.md](VEHICLE_QA_CHECKLIST.md)
- op助手：[OP_ASSISTANT_HANDOFF.md](OP_ASSISTANT_HANDOFF.md)
