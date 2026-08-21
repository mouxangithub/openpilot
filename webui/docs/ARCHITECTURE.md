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

## 测试与交接

- PC：[TESTING_PC_DEVICE_SCRCPY.md](TESTING_PC_DEVICE_SCRCPY.md)
- 上车：[VEHICLE_QA_CHECKLIST.md](VEHICLE_QA_CHECKLIST.md)
- op助手：[OP_ASSISTANT_HANDOFF.md](OP_ASSISTANT_HANDOFF.md)
