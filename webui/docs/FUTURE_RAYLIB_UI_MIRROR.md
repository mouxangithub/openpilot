# 未来项目：raylib 原生 UI 镜像投屏

> **状态**：规划文档，**不在当前 WebUI 仓库范围内实现**。  
> **当前主线**：继续完善 WebUI 对原生 BIG UI 的功能/视觉还原（见 [GUI_ALIGNMENT.md](./GUI_ALIGNMENT.md)）。  
> **相关**：PC/车机/scrcpy 对照测试见 [TESTING_PC_DEVICE_SCRCPY.md](./TESTING_PC_DEVICE_SCRCPY.md)。

---

## 1. 项目定位

### 1.1 要解决什么

在 PC/手机浏览器（或独立客户端）中：

- **观看**车机 openpilot **原生 raylib UI** 的实时画面（含 VisionIPC 相机、GPU shader、HUD、设置页）
- **可选**：远程触控回传到车机 UI 进程

### 1.2 不解决什么

| 不在范围内 | 说明 |
|------------|------|
| WebUI 像素 1:1 | WebUI 是 Web 复刻，见 [GAP_VS_DEVICE.md](./GAP_VS_DEVICE.md) |
| 替代 WebUI 设置流程 | Params/API/配对等仍由 WebUI 负责 |
| 相机单独 WebRTC | 已有 `teleoprtc` / `webrtcd`，与本项目「整帧 UI」不同 |

### 1.3 与 WebUI 的关系

```
                    ┌─────────────────────────────────────┐
  cereal / Params   │         车机 openpilot              │
                    │  ui 进程 (raylib 2160×1080)         │
                    └──────────┬────────────┬─────────────┘
                               │            │
              状态订阅 + API   │            │  帧抓取 / 编码
                               ▼            ▼
                    ┌──────────────┐  ┌──────────────────┐
                    │   WebUI      │  │ Raylib UI Mirror │  ← 本未来项目
                    │ (Web 复刻)   │  │ (真像素流)       │
                    └──────────────┘  └──────────────────┘
```

两条线**并行**：WebUI 做交互与对齐验收；Mirror 做「实体屏级」真画面远程观看。

---

## 2. 技术事实（基于 openpilot 源码）

### 2.1 车机 UI 渲染

| 项 | 值 / 行为 | 源码 |
|----|-----------|------|
| 逻辑分辨率 | **2160×1080**（tici/tizi `big_ui()`） | `system/ui/lib/application.py` |
| 设备 `SCALE` | 默认 **1.0** | 同上 |
| 设备 UI 帧率 | 默认 **~20 FPS**（tici/tizi） | `FPS` 环境变量 |
| 行车相机 | VisionIPC → GPU 纹理 → raylib 合成 | `selfdrive/ui/mici/onroad/cameraview.py` 等 |
| 抗锯齿 | `FLAG_MSAA_4X_HINT` | `application.py` |

**结论**：「整个 raylib」= 实体屏上看到的完整 UI，**包含**相机画面与所有 overlay，不是 WebUI 那套管线。

### 2.2 已有抓帧能力（可复用）

`RECORD=1` 时，每帧从 `RenderTexture` 读回 RGBA，经 ffmpeg 写 MP4：

```python
# openpilot/system/ui/lib/application.py (简化)
if RECORD:
    image = rl.load_image_from_texture(self._render_texture.texture)
    data = bytes(rl.ffi.buffer(image.data, w * h * 4))
    self._ffmpeg_queue.put(data)  # → ffmpeg stdin → output.mp4
```

环境变量（见 `system/ui/README.md`）：

| 变量 | 含义 |
|------|------|
| `RECORD=1` | 开启录屏 |
| `RECORD_OUTPUT` | 输出路径（默认 `output.mp4`） |
| `RECORD_QUALITY` | x264 CRF（默认 23） |
| `RECORD_BITRATE` | 可选固定码率 |
| `OFFSCREEN=1` | 无窗口快速离线渲染 |

**现状**：仅**离线录文件**，无直播、无 WebRTC、无远程触控。

### 2.3 外部方案：scrcpy

| 项 | 说明 |
|----|------|
| 抓什么 | DRM/KMS **最终上屏** framebuffer |
| 与 RECORD 差异 | 可能经过显示缩放；RECORD 抓 raylib 内部纹理 |
| 设备 `SCALE=1` 时 | 两者观感应非常接近 |
| 触控 | ADB 注入，**物理屏坐标**，与 WebUI 2160 逻辑坐标无关 |
| 集成 | 不依赖 openpilot 改代码；适合调试金标准对照 |

---

## 3. 「1:1」能到什么程度（诚实边界）

| 层级 | 是否可达 | 说明 |
|------|----------|------|
| **逻辑分辨率 1:1** | ✅ | 2160×1080 帧缓冲可抓 |
| **内容完整** | ✅ | 相机 + HUD + 设置同一帧 |
| **远程观感 1:1** | 🟡 | H.264/WebRTC 有压缩、延迟、色偏 |
| **比特级无损远程** | ❌ | 网络编码必然有损 |
| **60 FPS 流畅远程** | 🟡 | 车机 UI 默认 20 FPS；提 FPS + 编码会吃 GPU |

**WebUI 永远不能替代本项目的「真 raylib 像素流」**——架构分叉（VisionIPC vs WebRTC、GPU shader vs WebGL2、raylib vs DOM）。

---

## 4. 方案对比（新项目选型）

| 方案 | 描述 | 真 raylib | 开发量 | 性能风险 | 推荐 |
|------|------|-----------|--------|----------|------|
| **A. scrcpy 文档化** | 不改代码，运维用手动 scrcpy | ✅ 上屏 | 0 | 低 | 现状金标准 |
| **B. RECORD → 直播** | 扩展 `RECORD` 管线，ffmpeg → WebRTC/LL-HLS | ✅ 纹理 | 中 | **高**（GPU 回读） | **MVP 首选** |
| **C. 共享纹理 / dma-buf** | 零拷贝导出 RenderTexture | ✅ | 高 | 中 | 长期优化 |
| **D. cereal 帧广播** | UI 进程 JPEG/H264 编码后发 cereal | ✅ | 中高 | 中 | 与 B 类似 |
| **E. WebUI 内嵌 scrcpy** | 网页解码 ADB 流 | ✅ 上屏 | 高 | 中 | **不推荐**（两套坐标系） |

---

## 5. 推荐架构（新项目 MVP）

### 5.1 模块划分

```
┌─────────────────────────────────────────────────────────────┐
│ ui 进程 (openpilot 侧，最小 patch)                           │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐ │
│  │ raylib 渲染  │───►│ FrameSource  │───►│ Encoder (x264)  │ │
│  │ RenderTexture│    │ (RGBA 队列)  │    │ 或硬件编码       │ │
│  └─────────────┘    └──────────────┘    └────────┬────────┘ │
└──────────────────────────────────────────────────│──────────┘
                                                   │ RTP / WebRTC
┌──────────────────────────────────────────────────▼──────────┐
│ mirror-server（独立 repo 或 openpilot 可选服务）              │
│  - WebRTC 发布（可复用 teleoprtc 模式）                       │
│  - 鉴权 Token / 仅局域网                                      │
│  - 可选：TouchIngress → cereal uiTouchInject                 │
└──────────────────────────────────────────────────┬──────────┘
                                                   │
┌──────────────────────────────────────────────────▼──────────┐
│ mirror-client（浏览器或 Electron）                            │
│  - `<video>` 或 WebRTC 收流                                   │
│  - 全屏 2160×1080 或 fit 窗口                                 │
│  - 可选：pointer → 逻辑坐标 → POST /touch                     │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 openpilot 侧最小改动（建议）

1. **抽象 `FrameSource`**：从 `RECORD` 分支抽出，支持 `file | pipe | callback`
2. **环境变量** `UI_MIRROR=1`：启用帧回调，不默认开（避免量产性能损耗）
3. **可选** `log.capnp` 增加 `uiTouchInject`（远程触控，Phase 2）
4. **不改** WebUI 代码路径

### 5.3 性能预算（tici 经验值，需实测）

| 操作 | 粗估成本 |
|------|----------|
| `load_image_from_texture` 2160×1080 | ~5–15 ms/帧（GPU 回读） |
| x264 veryfast 1080p | ~10–30 ms/帧（CPU） |
| 合计 @20 FPS | 可能接近或超过预算 → 需降分辨率、硬件编码或降 FPS |

**缓解**：

- 镜像流用 **1280×720** 子采样（非严格 1:1，但流畅）
- 仅 **Offroad / 调试** 时开启 `UI_MIRROR`
- 探索 **MediaCodec** 硬件编码（AGNOS）

---

## 6. 远程触控（可选 Phase 2）

与 [TESTING_PC_DEVICE_SCRCPY.md §6](./TESTING_PC_DEVICE_SCRCPY.md) 一致，摘要如下：

| 层级 | 内容 | 工作量 |
|------|------|--------|
| L1 | 浏览器操作 WebUI | ✅ 已有，非本项目 |
| L2 | 客户端坐标 → 2160×1080 映射 | ~3–4 人日 |
| L3 | 注入 raylib `MouseEvent`（cereal + ui 互斥） | ~10–12 人日 MVP |
| scrcpy 触控 | 物理坐标，独立于本项目 | 用 ADB 即可 |

**Mirror 项目若做触控**：客户端按 **2160×1080 逻辑坐标** 发送；服务端注入 ui 进程，并与实体触控互斥（建议仅 Offroad 或 Param 开关）。

---

## 7. 里程碑（建议新项目 Backlog）

### Phase 0 — 调研（2–3 天）

- [ ] 车机上 `RECORD=1` 录 30s 行车/设置，确认分辨率与码率
- [ ] 对比 scrcpy 截图 vs RECORD 截图（SSIM/肉眼）
- [ ] 测 `load_image_from_texture` 单帧耗时（`PROFILE_RENDER`）
- [ ] 确认 teleoprtc 是否可复用为「非相机」视频轨

### Phase 1 — MVP 观看（1–2 周）

- [ ] 从 `application.py` 抽出 `FrameSource` 接口
- [ ] `UI_MIRROR=1` + 命名管道 / Unix socket 输出 RGBA 或 NV12
- [ ] 独立 `mirror-server`：ffmpeg 或 gstreamer → WebRTC
- [ ] 浏览器单页全屏播放；局域网鉴权
- [ ] 文档：启动方式、与 WebUI 端口不冲突（如 WebUI 5080，Mirror 5081）

### Phase 2 — 可用性（+1 周）

- [ ] 断线重连、码率自适应
- [ ] 720p 子流选项（流畅优先）
- [ ] Param `UiMirrorEnabled` 车机开关

### Phase 3 — 触控（+2 周，可选）

- [ ] `uiTouchInject` cereal + ui 消费
- [ ] 客户端坐标映射 + 安全白名单
- [ ] Offroad 设置页 E2E 验证

### Phase 4 — 优化（可选）

- [ ] 硬件编码
- [ ] dma-buf / 减少回读
- [ ] 多观看端

---

## 8. 验收标准（新项目）

| ID | 场景 | 通过条件 |
|----|------|----------|
| M01 | 离路 Home | 远程画面与 scrcpy 同场景肉眼一致（允许压缩差） |
| M02 | 行驶 engaged | 速度/告警/车道线与实体屏同步（延迟 <300ms LAN） |
| M03 | 设置页滚动 | 列表滚动流畅，无明显花屏 |
| M04 | 弱网 | 降码率不崩溃，可恢复 |
| M05 | 关闭 Mirror | `UI_MIRROR=0` 后 UI FPS 与功耗恢复基线 |
| M06 | 与 WebUI 共存 | 5080 WebUI + 5081 Mirror 同时可用 |

---

## 9. 风险与决策记录

| 风险 | 影响 | 对策 |
|------|------|------|
| GPU 回读拖慢 ui 进程 | 实体屏卡顿 | 默认关闭；降分辨率；Offroad only |
| 与 WebUI 定位重叠 | 重复建设 | WebUI = 设置/对齐；Mirror = 真画面 |
| 安全 | 未授权遥控 | Token + 局域网 + 触控 Phase 独立开关 |
| 维护 fork 成本 | openpilot 升级冲突 | FrameSource 尽量小 patch，上游 PR 或独立 daemon attach |

---

## 10. 快速命令备忘

```bash
# 现有：UI 录屏（离线）
RECORD=1 RECORD_OUTPUT=/data/ui_capture.mp4 python3 ...

# 现有：PC WebUI 预览（非 raylib）
py -3 webui/dev/run_pc.py --port 5080

# 现有：车机 WebUI（Web 复刻，非镜像）
python3.12 -m webui.webuid --host 0.0.0.0 --port 5080

# 对照金标准：scrcpy
scrcpy -s <serial> --max-size 1920

# 未来（示意，未实现）
UI_MIRROR=1 UI_MIRROR_URL=ws://127.0.0.1:5081/stream ...
```

---

## 11. 相关文档索引

| 文档 | 用途 |
|------|------|
| [GUI_ALIGNMENT.md](./GUI_ALIGNMENT.md) | **当前** WebUI 对齐清单（v74+） |
| [GAP_VS_DEVICE.md](./GAP_VS_DEVICE.md) | WebUI vs raylib 管线差异 |
| [TESTING_PC_DEVICE_SCRCPY.md](./TESTING_PC_DEVICE_SCRCPY.md) | PC / 车机 / scrcpy 测试与触控工作量 |
| `openpilot/system/ui/README.md` | RECORD / BURN_IN 等 UI 环境变量 |

---

## 12. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-14 | 初版：从 WebUI 对话整理，标记为未来独立项目 |
