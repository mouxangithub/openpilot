# WebUI WebRTC 直播优化方案

> **版本**：v1.0  
> **适用范围**：Sunnylink / openpilot WebUI 行车预览、驾驶员监控预览  
> **核心约束**：**不得影响 openpilot 正常上路辅助驾驶**；所有优化仅作用于直播旁路（`stream_encoderd` / `webrtcd` / 浏览器），安全优先级永远高于画质与流畅度。

---

## 1. 设计原则

### 1.1 安全优先（不可妥协）

| 优先级 | 对象 | 说明 |
|--------|------|------|
| P0 | `modeld` / `controlsd` / `plannerd` / `pandad` | 感知、规划、控制——**禁止为直播做任何改动** |
| P0 | `encoderd` 主路编码 | 行车日志 `roadEncodeData`（HEVC）——与直播无关，**禁止合并或降优先级** |
| P0 | `camerad` 采集参数 | 曝光、帧率、缓冲影响所有视觉消费者——**禁止为直播单独改 camerad** |
| P1 | `stream_encoderd` | 直播专用 H.264 编码——可降码率/按需启停，但需监控是否造成 ISP/GPU 争抢 |
| P2 | `webrtcd` + 浏览器 | 纯观看路径——可激进优化 |
| P3 | WebUI `model_overlay` | 仅读 `modelV2` 做 2D 投影——可降频或关闭，**不影响驾驶** |

### 1.2 优化决策顺序

```
驾驶安全与主路进程稳定
    → 设备热/CPU 余量（若不足则先降直播负载）
    → 网络质量（自动降码率）
    → 浏览器解码与渲染（降 overlay 频率）
    → 画质与首帧延迟（最后才考虑）
```

### 1.3 隔离保证

openpilot 已将直播与驾驶路径**物理隔离**：

```
camerad（采集，onroad 本就会运行）
    ├── encoderd          → roadEncodeData（HEVC，日志/主路）  ← 驾驶关键
    └── stream_encoderd   → livestream*EncodeData（H.264）    ← 仅直播
                                    ↓
                              webrtcd → 浏览器
```

- 直播码率通过 `LivestreamEncoderBitrate` 写入，**只**被 `stream_encoderd` 的 `is_live` 编码器读取。
- WebUI 的 `webrtc_enable` 仅写 `IsLiveStreaming`，启停 `stream_encoderd` / `webrtcd`，**不写任何控制相关 Param**。

---

## 2. 架构与数据流

### 2.1 设备端进程

| 进程 | 启动条件 | 职责 |
|------|----------|------|
| `camerad` | `started \|\| IsDriverViewEnabled \|\| IsLiveStreaming` | 相机采集 |
| `encoderd` | `only_onroad` | 主路 HEVC 编码 + qcam |
| `stream_encoderd` | `IsLiveStreaming \|\| notcar` | 直播 H.264（road / wide / driver 三路） |
| `webrtcd` | 同上 | WebRTC 信令 + RTP 发送 + 码率自适应 |

关键文件：

- `openpilot/system/webrtc/webrtcd.py` — 会话、`LivestreamBitrateController`
- `openpilot/system/webrtc/device/video.py` — 从 cereal 读 H.264 NAL
- `openpilot/system/loggerd/encoderd.cc` — `encoder_set_bitrate()` 读 `LivestreamEncoderBitrate`
- `openpilot/system/loggerd/loggerd.h` — `StreamEncoderSettings()`（H.264，GOP=5，默认 5 Mbps）
- `webui/server/bridge/webrtc_api.py` — SDP/notify HTTP 代理
- `webui/web/static/js/webrtc_stream.js` — 浏览器客户端

### 2.2 浏览器端

```
RTCPeerConnection
    → #road-video（H.264 解码）
    → #model-overlay canvas（WebSocket model_overlay 或 HTTP 轮询，与 RTP 无关）
    → HUD（仅在 is-playing 后显示）
```

### 2.3 码率档位（现有）

`LivestreamBitrateController`（`webrtcd.py`）：

| 标签 | 码率 | 触发方式 |
|------|------|----------|
| `low` | 500 kbps | 手动或 auto 降档 |
| `med` | 1.5 Mbps | 浏览器当前默认（`tuneStreamForBrowser()`） |
| `high` | 5 Mbps（可用 `STREAM_BITRATE` 环境变量覆盖） | auto 最高档 |
| `auto` | 根据 RTP `fraction_lost` 在三档间切换 | 丢包 ≥5% 持续降档，=0 升档 |

自适应采样周期：**200ms**。写 Param：`LivestreamEncoderBitrate`。

### 2.4 为何驾驶员监控比行路画面更流畅？

| 因素 | 行路 WebRTC | 驾驶员监控 |
|------|-------------|------------|
| 分辨率 | 1928×1208 级前路 | 驾驶员相机通常更低 |
| 码率 | med/high，叠加 overlay | 同连接切 track 时几乎无重连 |
| 前端负载 | canvas 车道线 + HUD 刷新 | 纯 video 全屏 |
| 编码路数 | road/wide 可能切换 | driver 单路 |

这不是 bug，而是**负载差异**。优化应让行路预览向驾驶员监控的「轻量」靠拢，而不是动驾驶栈。

---

## 3. 延迟与卡顿根因

### 3.1 端到端链路

```
采集(20fps) → stream_encoder(GOP=5, ~250ms) → cereal → webrtcd → Wi-Fi RTP
    → 浏览器 jitter buffer → H.264 软解 → compositor → canvas overlay
```

典型延迟贡献（经验值，因网络而异）：

| 环节 | 大约延迟 | 可优化？ |
|------|----------|----------|
| 首次 SDP 握手 | 5–30s（冷启动 webrtcd） | ✅ 预热 |
| 编码 + GOP | 250–500ms | ⚠️ 仅直播 GOP，不动主路 |
| Wi-Fi RTP + 丢包重传 | 100ms–2s | ✅ 降码率 |
| 浏览器 jitter buffer | 100–300ms | ⚠️ 有限 |
| overlay 绘制 | 16–50ms/帧 | ✅ 降频 |

### 3.2 常见症状对照

| 现象 | 可能原因 | 安全侧检查 |
|------|----------|------------|
| 首次打开很慢 | webrtcd 冷启动、ICE 收集 | 确认未阻塞 manager 拉起主进程 |
| 持续卡顿 | 码率过高 / Wi-Fi 弱 | 查 `fraction_lost`，先 auto 降档 |
| 偶发冻结后恢复 | 丢包触发关键帧 | 正常，直播路径 |
| 画面糊 | 已降档到 low | 预期行为，安全优先 |
| 设备发热严重 | 三路 stream 编码同时跑 | 考虑按需只编码当前相机 |

---

## 4. 优化方案（按层）

### 4.1 浏览器 / WebUI 前端（✅ 最安全，优先实施）

| 方案 | 说明 | 状态 | 安全影响 |
|------|------|------|----------|
| **预热 webrtcd** | 页面加载后 `prewarmWebrtc()`，减少首次 SDP 等待 | 已实现 | 无 |
| **默认 med 码率** | 连接后 `livestreamSettings: { quality: "med" }` | 已实现 | 无 |
| **HUD 延后显示** | `is-playing` 前隐藏时速等 | 已实现 | 无 |
| **overlay 延后/降频** | 相机播放后再画；WS 连接时停 HTTP 轮询 | 部分实现 | 无 |
| **画质档位 UI** | 用户选 流畅(low) / 标准(med) / 高清(high) / 自动(auto) | 待做 | 无 |
| **弱网自动切 auto** | 检测到 `navigator.connection` 为 2g/slow-2g 时默认 low | 待做 | 无 |
| **标签页隐藏降载** | `document.hidden` 时暂停 overlay、可选 `livestreamVideoEnable: false` | 待做 | 无 |
| **驾驶员弹窗复用连接** | 行路已播时只 `livestreamCameraSwitch` | 已实现 | 无 |

**推荐默认策略（上路）**：

```javascript
// 伪代码 — 连接成功后
await notifyWebrtc({ type: "livestreamSettings", data: { quality: "auto" } });
// auto 从 med/high 起步，丢包时自动降到 low，不影响设备端驾驶
```

若仍卡顿，UI 提供「流畅模式」一键 `quality: "low"`。

### 4.2 WebUI 服务端（✅ 安全）

| 方案 | 说明 | 安全影响 |
|------|------|----------|
| **model_overlay 10Hz → 5Hz** | `ws_handler` 推送间隔加大 | 无，仅预览 |
| **HTTP overlay 轮询 ≥500ms** | 弱网时减少 Python 投影计算 | 无 |
| **弱设备跳过 overlay** | `deviceState` 高温时返回空 overlay | 无 |
| **SDP 代理超时调优** | 避免过早失败重试风暴 | 无 |

### 4.3 webrtcd（⚠️ 仅直播，需路测）

| 方案 | 说明 | 风险 |
|------|------|------|
| **上路默认 auto + 初始 med** | `set_quality("auto")` 且 level 从 1 开始 | 低 |
| **更保守的降档阈值** | `med_level` 从 0.05 调到 0.03，更快降码率 | 低，仅画质 |
| **升档更慢** | `up_samples` 加大，避免码率震荡 | 低 |
| **单会话 teardown** | 无观看者 5s 后 `IsLiveStreaming=False` | 已有，减设备负载 |
| **timing SEI** | 调试延迟用，生产可关 | 极低 |

**禁止**：修改 `StreamSession` 去桥接 `carState` 到浏览器（WebUI 已刻意 `bridge_services=[]`，避免额外汇聚负载）。

### 4.4 stream_encoderd（⚠️ 需谨慎路测）

| 方案 | 说明 | 风险 |
|------|------|------|
| **按需编码** | 仅编码当前 `livestreamCameraSwitch` 选中的路，其余暂停 | 中——需改 encoderd，要测 ISP 负载 |
| **环境变量 `STREAM_BITRATE`** | 上限从 5M 降到 3M | 低——仅直播 |
| **GOP 5→3** | 降低延迟，略增码率波动 | 中——需回归测试 |
| **encoder lag 监控** | 日志已有 `encoder lag`，若频繁出现应主动降直播码率 | 低 |

**禁止**：降低 `main_road_encoder_info` 码率或合并 `encoderd` 与 `stream_encoderd`。

### 4.5 设备资源保护（上路自动降载）

当满足以下**任一**条件时，**仅**降低直播质量（不碰驾驶）：

| 信号 | 来源 | 建议动作 |
|------|------|----------|
| RTP 丢包率高 | `LivestreamBitrateController` | auto 降档（已有） |
| 设备高温 | `deviceState.thermalStatus` | notify `quality: low` + 停 overlay |
| CPU 占用高 | `/proc` 或现有监控 | notify `quality: low` |
| `stream_encoderd` lag 日志 | encoderd LOGE | 降 `LivestreamEncoderBitrate` |
| 用户未在看 | 浏览器 hidden / 无 WS 订阅 | `webrtc_disable` 或 `livestreamVideoEnable: false` |

---

## 5. 自动降码率策略（推荐实现）

### 5.1 多信号融合状态机

```
                    ┌─────────────────┐
                    │  上路 engaged   │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │ 直播是否活跃？              │
              │ (IsLiveStreaming && 有观众) │
              └──────────────┬──────────────┘
                     否     │     是
              ┌─────────────┴─────────────┐
              ▼                           ▼
         不处理                      采集健康信号
                                    ├─ RTP loss (webrtcd)
                                    ├─ 热状态 (deviceState)
                                    ├─ 浏览器 hidden
                                    └─ encoder lag (可选)
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │ 任一项超阈值？         │
                              └───────────┬───────────┘
                                    是    │    否
                              ┌───────────┴───────────┐
                              ▼                       ▼
                    quality → low              quality → auto/med
                    overlay off                overlay on
                    (仅 LivestreamEncoderBitrate)
```

### 5.2 阈值建议（初版）

| 信号 | 降档条件 | 恢复条件 |
|------|----------|----------|
| RTP `fraction_lost` | ≥5% 持续 1s → med；≥10% 立即 → low | ≤0 持续 5s 升一档 |
| 热状态 | `thermalStatus >= yellow` → low | `< green` 持续 30s → med |
| 标签页隐藏 | `livestreamVideoEnable: false` | visible 后恢复 + 请求关键帧 |
| overlay | 丢包 >5% 或 low 档 | med 以上恢复 |

### 5.3 实现落点

| 组件 | 职责 |
|------|------|
| `webrtcd.py` `LivestreamBitrateController` | RTP 丢包自适应（已有，可微调阈值） |
| `webrtc_stream.js` | 读 `deviceState`（bootstrap/WS），notify `livestreamSettings` |
| `app.js` | `document.visibilitychange` → 暂停视频/overlay |
| `webui` 可选守护 | 读 thermal，HTTP 推送给前端 |

**关键**：所有降码率操作只写 `LivestreamEncoderBitrate` 或发 `livestreamSettings`，**绝不写** `IsEngaged`、模型、控制相关 Param。

---

## 6. 实施路线图

### Phase 0 — 已完成

- [x] 预热 webrtcd
- [x] 默认 med 码率
- [x] HUD / overlay 延后
- [x] 驾驶员监控 UI + i18n
- [x] WS 连接时停 HTTP overlay 重复轮询

### Phase 1 — 低风险（已完成）

1. [x] **浏览器默认 `auto`**，初始档位 med（1.5M），丢包自动降 low  
2. [x] **设置页增加「预览画质」**：流畅 / 标准 / 高清 / 自动（存 `localStorage`）  
3. [x] **`document.hidden` 时暂停 overlay 绘制** + `livestreamVideoEnable: false`  
4. [x] **弱网/高温提示**：降档时 toast

### Phase 2 — 设备侧增强（已完成）

1. [x] **webrtcd 降档阈值微调**（med_level 0.03，down_samples 3，初始 med）  
2. [x] **高温联动**：`thermal overheated/critical` → 强制 low + 关 overlay  
3. [x] **直播诊断**：`GET /api/opui/stream/health` + Device 面板  
4. [x] **直播上限默认 3 Mbps**（`STREAM_BITRATE` / `loggerd.h`）

### Phase 3 — 架构级（已完成）

1. [x] **按需编码**：`LivestreamActiveCamera` + `encoderd` 跳过非活跃路  
2. [x] **WebCodecs 硬解**：`webrtc_webcodecs.js` + Device 面板「硬件解码」开关（不支持时自动回退 `<video>`）  
3. [x] **overlay 与视频解耦**：WS 按 fps 推送（5/10/15Hz），高温跳过投影  
4. [x] **encoder lag 联动**：`LivestreamEncoderLagging` → webrtcd 强制 low + 前端 toast  
5. [x] **CPU/内存自动降档**：内存 ≥85% 或 CPU ≥92°C → 流畅模式

---

## 7. 禁止触碰清单

| 操作 | 原因 |
|------|------|
| 修改 `encoderd` 主路 HEVC 码率/GOP | 影响行车日志与回放 |
| 合并 `stream_encoderd` 与 `encoderd` | 破坏进程隔离 |
| 为直播调整 `camerad` 帧率/分辨率 | 影响 modeld 感知 |
| 在 engaged 时随意改 `IsDriverViewEnabled` | 影响 dmonitoring / pandad |
| 通过 WebRTC 桥接控制消息到车 | 安全风险 |
| 直播降载时降低 `modeld` 频率 | 直接危害安全 |
| 在 Wi-Fi 差时阻塞 `controlsd` 网络 | 不存在但需避免任何类似设计 |

---

## 8. 验证与监控

### 8.1 路测检查项

- [ ] engaged 时开关 WebUI 预览，**转向/制动/巡航无异常**  
- [ ] 弱网下降码率后，**qlog 主路视频完整**（与直播无关）  
- [ ] 长时间预览后设备温度，对比不开预览的基线（ΔT 可接受）  
- [ ] `stream_encoderd` 日志无持续 `encoder lag`  
- [ ] 关闭预览后 `IsLiveStreaming=False`，进程退出

### 8.2 建议指标

| 指标 | 采集点 | 目标 |
|------|--------|------|
| 首帧时间 | 浏览器 `playing` 事件 − 点击 | 冷启动 <15s（预热后 <3s） |
| 端到端延迟 | timing SEI（调试） | <800ms（med/low） |
| RTP 丢包率 | webrtcd stats | <5% 常态 |
| overlay FPS | canvas `requestAnimationFrame` | 10–15fps 足够 |
| 直播码率 | `LivestreamEncoderBitrate` | 随档位变化 |

### 8.3 调试命令（设备 SSH）

```bash
# 查看 webrtcd 是否在监听
ss -tlnp | grep 5001

# 当前直播 Param
grep -E 'IsLiveStreaming|LivestreamEncoderBitrate' /data/params/d/

# stream_encoderd 日志
tail -f /data/log/swaglog.* | grep -E 'stream_encoderd|encoder.*lag'

# 手动设直播码率上限（仅直播，重启后失效除非写 env）
STREAM_BITRATE=1500000  # 在 manager 环境或 service 中配置
```

---

## 9. 配置速查

| 配置 | 位置 | 作用域 |
|------|------|--------|
| `IsLiveStreaming` | Params | 启停直播进程 |
| `LivestreamEncoderBitrate` | Params（运行时） | 仅 stream_encoderd |
| `LivestreamRequestKeyframe` | Params | 仅直播 IDR |
| `STREAM_BITRATE` | 环境变量 | 直播 high 档上限 + 初始编码 |
| `livestreamSettings.quality` | WebRTC datachannel/notify | low/med/high/auto |
| `livestreamCameraSwitch` | notify | road/wideRoad/driver |
| `livestreamVideoEnable` | notify | 暂停/恢复 RTP 视频 |

---

## 10. 总结

WebRTC 优化的正确姿势是：**把直播当作可牺牲的旁路**，在任何资源紧张或网络变差时，先砍直播码率和 overlay，再砍预览帧率，最后才考虑关预览；**永远不要动驾驶主路径**。

现有架构已经具备安全的自动降码率基础（`LivestreamBitrateController` + 独立 `stream_encoderd`）。下一步最高性价比的工作在**浏览器侧**：默认 `auto`、可见性降载、画质档位 UI，以及**高温/弱网联动降档**——这些改动零风险，且能明显改善你遇到的卡顿与延迟问题。

如需按 Phase 1 落地代码，可在 `webrtc_stream.js` + 设置面板中实现，无需修改 openpilot 核心。
