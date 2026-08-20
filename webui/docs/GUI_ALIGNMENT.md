# WebUI ↔ 原生 BIG GUI 对齐清单

> 画布：**2160×1080**（`openpilot/system/ui` BIG UI）  
> 对照源码：`openpilot/selfdrive/ui/onroad/*`、`sunnypilot/onroad/*`、`layouts/sidebar.py`、`layouts/home.py`  
> Web 实现：`webui/web/static/*`、`webui/server/bridge/*`  
> 相关：`webui/docs/GAP_VS_DEVICE.md`（管线级差异）

**图例**：✅ 行为/布局已对齐 · 🟡 近似实现（非像素 1:1）· ❌ 未实现 · ⛔ 架构性不可 1:1

**最后更新：2026-08-14（v78）**

---

## 0. 总览：对齐到什么程度？（诚实评估）

**WebUI 不是 1:1 像素还原。** 目标是：**同一套 cereal/Params 规则下，行车 HUD 与设置流程与车机一致**；绘制层用 **WebRTC + WebGL/Canvas + DOM** 近似 raylib + VisionIPC。

| 维度 | v78 估计 | 说明 |
|------|----------|------|
| **功能 / 状态机** | **~97–98%** | v78 onboarding + i18n 补全 |
| **布局 / 视觉** | **~90–93%** | v78 fade/边框/动效抛光 |
| **动效** | **~88–91%** | v78 SLA/SCC/E2E/ICBM 对齐 |
| **渲染管线** | **~50–58%** | ⛔ 仍非 VisionIPC |

| 范围 | 功能 | 视觉 |
|------|------|------|
| **行车 HUD** | ~98% | ~90% |
| **离路 Home + 侧栏** | ~92% | ~84% |
| **设置 15 面板** | ~95% | ~87% |
| **全产品** | **~95%** | **~88%** |

---

## 1. v78 新增（抛光）

| 区域 | 项 | 状态 |
|------|-----|------|
| 边框 | 圆角 **0.12** | ✅ |
| 相机 | `onroad_fade.png` 底部渐隐 | ✅ |
| SLA/SCC | `AlertFadeAnimator` 淡入 | ✅ |
| E2E | 帧同步脉冲（非 CSS step） | ✅ |
| ICBM | 3s 墙钟保持 | ✅ |
| 模型 | 路沿 `1 - std` alpha | ✅ |
| Home | UPDATE/ALERTS i18n | ✅ |
| 引导 | Web onboarding API + UI | ✅ |
| op助手 | `webui_list_dev_presets`、`webui_onboarding_status` | ✅ |

**部署**：强刷 `?v=78`。P0 overlay 仍待上车。

---

## 2. v77 新增

| 区域 | 项 | 状态 |
|------|-----|------|
| 模型 | WebGL path/lead 多层光晕；mock 前车 chevron | ✅ |
| 侧栏 | Wi-Fi 类型显示分级图标（`wifi_strength_*.png`）+ 圆点 | ✅ |
| OSM | 内置 **173 国 + 56 州** 全量离线 JSON；`full` 标记 | ✅ |
| OSM | 修复 `_save_disk_cache` / `_shm_params` | ✅ |
| 动效 | 扭矩条 rAF + 真实 dt；DM arc fade 一阶滤波 | ✅ |
| 触控 | `opui_coords.js` 逻辑坐标映射；`touch-action` | ✅ |
| Dev | `confidence_low/high`、`onroad_overlay` 预设 | ✅ |

**部署**：强刷 `?v=77`。

**测试与交接**：`TESTING_PC_DEVICE_SCRCPY.md`、`OP_ASSISTANT_HANDOFF.md`、`VEHICLE_QA_CHECKLIST.md`

---

## 2. v76 新增

| 区域 | 项 | 状态 |
|------|-----|------|
| HUD | `hud_confidence.js` + `state_api._confidence_ball()`（mici 特性，右缘置信度球） | ✅ |
| 模型 | WebGL 车道双层 `expandPoly` 光晕近似 shader AA | 🟡 |
| 模型 | mock overlay 梯形车道 polygon + path 中心线 | ✅ |
| OSM | 磁盘缓存 `_CACHE_DIR`（成功写入、失败读缓存→内置包→mock） | ✅ |
| OSM | 设置面板 `bundled`/`cached` toast 提示 | ✅ |
| Home | Prime ✓ 使用 `icons/checkmark.png`（未订阅/已订阅） | ✅ |

**部署**：强刷 `?v=77`（v76 为 `?v=76`）。

---

## 3. v75 新增

| 区域 | 项 | 状态 |
|------|-----|------|
| E2E | `hud_circular.js`：绿灯 / 前车驶离 / STOPPED 计时（对齐 `circular_alerts.py`） | ✅ |
| E2E | 3s 显示计时、脉冲环、Dev UI 右栏偏移 `--dev-ui-adj` | ✅ |
| OSM | 内置 `data/osm_*.json` 弱网/离线回退（20 国 + 20 州） | ✅ |
| i18n | E2E 文案 `GREEN\nLIGHT` / `LEAD VEHICLE\nDEPARTING` / `STOPPED` | ✅ |
| 修复 | 补全缺失的 `hud_circular.js`（此前 onroad 导入会 404） | ✅ |

**部署**：强刷 `?v=76`（v75 为 `?v=75`）。

---

## 3. v74 新增

| 区域 | 项 | 状态 |
|------|-----|------|
| 路名 | 动态宽度 + marquee（对齐 mici `onroad_info_panel`） | ✅ |
| 路名 | `liveMapDataSP.roadName` 兜底 | ✅ |
| 告警 | mid 高度 `wrap_text` + 动态 `min-height` | ✅ |
| 转向 | rAF + `exp(-dt/rc)` 滤波（对齐 `turn_signal.py`） | ✅ |
| 扭矩 | FirstOrder 步进 `rc=0.1` | ✅ |
| Overlay | 移除 `started_frame` 门控（减少「没线」） | ✅ |
| Overlay | WS 断开自动 HTTP 轮询兜底 | ✅ |
| SunnyLink | QR 弹窗 + `qrcode` 后端生成 | ✅ |
| OSM | 网络失败时 mock/缓存回退 | ✅ |
| Wi-Fi | mici 强度图标 + slash | ✅ |
| i18n | 侧栏网络类型、Home 预览、Dev 预设英文占位 | ✅ |

**部署**：强刷 `?v=74`。

---

## 2. v73 新增

| 区域 | 项 | 状态 |
|------|-----|------|
| 模型 | `model_webgl.js` WebGL2 车道/路径/前车 + Canvas 指标文字层 | ✅ |
| 模型 | Chevron 指标锚点/字号对齐 `chevron_metrics.py`（`d_rel`→`sz`） | ✅ |
| DM | 椭圆姿态弧 spline 点（`dm_snapshot` + SVG polyline） | ✅ |
| 扭矩 | `arc_bar_pts` 圆角厚弧 + 渐变填充（对齐 `torque_bar.py`） | ✅ |
| 限速 | 维也纳红环宽度 `18px`（≈ `outer_radius×0.18`） | ✅ |
| Dev | 预设按钮 i18n（`dev.js` + `webui_i18n`） | ✅ |
| 杂项 | `favicon.svg` | ✅ |

**部署**：`git pull` 后强刷 `?v=73`。

---

## 2. v72 新增

| 区域 | 项 | 状态 |
|------|-----|------|
| 告警 | 合成告警 `alert_resolve.py`（Unavailable / Unresponsive / TAKE CONTROL） | ✅ |
| 限速 | 英制 MUTCD 牌圆角 `min(w,h)×0.35`（JS 动态） | ✅ |
| 转向 | 转向灯 `FirstOrderFilter` 式闪烁（~80 BPM） | ✅ |
| DM | 姿态弧 `arc_thickness_h/v` + `fade` 衰减 | ✅ |
| 文档 | 本文件总览 + 缺口表校正（去除虚假 ✅） | ✅ |

**部署**：`git pull` 后强刷 `?v=72`。

---

## 3. v71 新增（行车 HUD 核心缺口）

| 区域 | 项 | 状态 |
|------|-----|------|
| 限速 | `speed_limit_mode` + 完整 `sp_hud` 字段；Off 时隐藏独立牌 | ✅ |
| DM | `dm_snapshot.py`：人脸 spline、`pose_h/v`、`active`、`rhd` | ✅ |
| Dev UI | 底栏 `ACC./L.S./FRIC./L.A.F.` + 右栏着色/分支 | ✅ |
| 巡航 | 巡航框圆角 `0.35` | ✅ |
| Overlay | 流畅模式仍绘制（5fps），仅 critical/danger 热节流跳过 | ✅ |
| i18n | Dev HUD 标签中英文 | ✅ |

---

## 4. 仍为 🟡 / ❌ / ⛔ 的缺口（维护清单）

### 4.1 ⛔ 架构性（不计划 1:1）

| 项 | 原生 | WebUI |
|----|------|--------|
| 相机 | VisionIPC 直通 | WebRTC H.264 |
| 模型叠加 | GPU `ModelRenderer` shader | WebGL2 + Canvas 指标（数据同源） |
| 字体 | raylib 内嵌 | 浏览器 Inter 渲染 |
| 载体 | 2160×1080 物理屏 | 平板/浏览器 + 300px 指标侧栏 + `fitOpuiScale` |

### 4.2 🟡 行车 HUD（可继续抛光）

| 项 | 状态 | 说明 |
|----|------|------|
| 车道线/路径/前车 | 🟡 | WebGL 无 shader 级 AA；实车标定仍需验证 |
| 扭矩条 | 🟡 | 几何/滤波已对齐，帧率仍依赖浏览器 |
| E2E 圆环 | ✅ v75 | 绿灯/驶离/停车计时 |
| 置信度球 confidence ball | ✅ v76 | mici 右缘置信度球 |

### 4.3 🟡 / ❌ 离路 & 设置

| 项 | 状态 |
|----|------|
| OSM 区域树 | ✅ v77 | 173 国 + 56 州内置离线；联网成功写磁盘缓存 |
| Prime 勾选纹理 | ✅ v76 | `checkmark.png` |
| 侧栏 i18n | ✅ 网络类型已 `tr()` |

### 4.4 已校正的历史误标

| 文档旧项 | 实际 |
|----------|------|
| 合成告警 v48 ✅ | v72 前 ❌，现已 ✅ |
| 模型 shader 级 ✅ | 始终 🟡 Canvas |
| 车道线实车 ✅ | 🟡 待验证 |

---

## 5. 后续对齐优先级（Roadmap）

| 优先级 | 项 | 预期收益 |
|--------|-----|----------|
| P0 | 实车 overlay 标定验证 | 最后一道「没线」风险（需上车） |
| ~~P1~~ | ~~WebGL 抗锯齿 / path shader 近似~~ | ✅ v76–v77 多层光晕 |
| ~~P2~~ | ~~OSM 完整离线包~~ | ✅ v77 173 国 + 56 州 |
| ~~P3~~ | ~~confidence ball~~ | ✅ v76 |

---

## 6. 验证方式

```bash
# PC
py -3 webui/dev/run_pc.py --port 5080

# J3
PYTHONPATH=/data/openpilot:/usr/local/venv/lib/python3.12/site-packages \
  python3.12 -m webui.webuid --port 5080
```

1. 强刷 `?v=77`
2. Dev：`onroad_overlay` / `confidence_low` / `confidence_high` / `e2e_green` / `standstill_timer`
3. **限速**：`SpeedLimitMode=Off` → 独立牌隐藏
4. **Dev UI**：底栏 4 项 + 中文标签
5. **DM**：左下轮廓 + 姿态弧
6. **合成告警**：上路 5s 无 selfdriveState → `sunnypilot Unavailable`
7. **模型**：车道/路径（PC 用 `onroad_overlay`；真机标定仍需上车）

---

## 历史版本记录（v56 及以前）

<details>
<summary>展开 v56–v54 变更摘要</summary>


| 区域 | 项 | 状态 |
|------|-----|------|
| 设置 | `multiple_button` stacked（驾驶风格等）标题与分段按钮左对齐（`--segmented` + `align-items: flex-start`） | ✅ |
| 设置 | `simple_button` 宽度 800px 左对齐（对齐 `SIMPLE_BUTTON_WIDTH`） | ✅ |
| 设置 | 子面板去掉重复全宽「返回」条，仅保留顶栏 `‹` + 标题 | ✅ |
| 行车 | Dev UI 底栏 `bottom: 2×border`、z-index 高于边框，扭矩条随底栏上移 61px | ✅ |

**部署**：强刷 `?v=56`。

---

## v54 新增对齐项

| 区域 | 项 | 状态 |
|------|-----|------|
| 告警 | full 尺寸标题 top 200/270、副标题 bottom 361/420（对齐 `alert_renderer.py`） | ✅ |
| 模型 | 实验模式 `path_gradient` 后端序列化 + canvas 渐变绘制 | ✅ |
| 模型 | 非实验 `path_blend` 淡化（对齐 `_blend_filter`） | ✅ |
| i18n | 侧栏 Settings/Recording title、相机加载、确认对话框英文 key | ✅ |
| i18n | bootstrap 横幅英文 key + `tr()` | ✅ |

**部署**：`cd /data/openpilot/webui && git pull`，强刷 `?v=54`。

---

## v53 新增对齐项

| 区域 | 项 | 状态 |
|------|-----|------|
| 模型 | 标定单例、`path_polygon` 彩虹路径、HTTP 轮询兜底 | ✅ |
| 模型 | overlay 叠在 `#camera-wrap` 视频层上 | ✅ |
| 行车 | 车道线白色半透明（对齐原生） | ✅ |

**待上车验证**：车道线/彩虹路径实车显示。

---

## v51 新增对齐项

| 区域 | 项 | 状态 |
|------|-----|------|
| 视口 | 竖屏检测 `vh>vw` → `#opui-viewport` 旋转 90° + 按有效横屏尺寸缩放 | ✅ |
| Vehicle | `vehicle_brand_catalog.py` + `GET /api/opui/vehicle/brand-widgets`（Tesla/Toyota/Hyundai/Subaru） | ✅ |
| Cruise/SLA | `state_api.sla_available`；Assist 按钮门控（Tesla release / Rivian） | ✅ |
| Device | Reboot/Power Off engaged 拦截 + 确认对话框；Reset Calibration 确认 | ✅ |
| Software | Disable Updates 切换后 Reboot 确认流 | ✅ |
| Developer | Alpha Longitudinal rich 确认（AEB 警告文案） | ✅ |
| SunnyLink | 启用前 Consent 两步流程 + `CompletedSunnylinkConsentVersion` | ✅ |
| Models | 选模型仅 offroad 可用 | ✅ |

**部署**：`cd /data/openpilot/webui && git pull`，强刷 `?v=54`。

---


## 10. 修复优先级（执行顺序）

### P0 — 行车视觉核心
1. ✅ 告警布局/字号/圆角
2. ✅ 边框圆角公式
3. ✅ `model_canvas.js` 车道/路径 + 实验彩虹路径动画
4. ✅ HUD 渐变、限速位置、路名、ICBM 保持

### P1 — 交互与状态
5. ✅ Developer UI / 圆形 E2E 告警 / TorqueBar
6. ✅ Exp 按钮门禁与 hold 动画
7. ✅ 书签 + 麦克风侧栏
8. ✅ DM 弧点击 → driver cam

### P2 — 离路/设置
9. ✅ Home UPDATE/ALERTS 流
10. ✅ Sunnylink Sponsor/Pair
11. ✅ Cruise/Visuals 文案与 value_map、门控
12. ✅ Toggle 图标、Trips 图标、Audiowide 字体

### P3 — 抛光
13. 🟡 网络纹理图标（仍用圆点）、Prime 勾选资产
14. 🟡 i18n（侧栏标签仍部分中文硬编码）
15. ✅ Dev 预设：`long_only`、`alert_full`、`standstill_timer`

### 视频流（WebRTC）
- ✅ 行车 livestream（`process_config` + `webrtc_stream.js`）
- ✅ 进入 onroad 自动拉流（无手动按钮）
- ✅ 居中加载提示 + 旋转指示
- ✅ 实验模式 wideRoad/road 车速滞回切换
- ✅ 驾驶员监控（notify 切 `driver` + 快路径复用 road 流）
- ✅ 页面加载 `prewarmWebrtc()`

---

## v48 新增对齐项

| 区域 | 项 | 状态 |
|------|-----|------|
| 告警 | 合成告警（Unavailable / Unresponsive / TAKE CONTROL） | ✅ `state_api._resolve_alert` + `tr()` |
| DM | 人脸轮廓 spline（33 keypoints） | ✅ `face_outline` + SVG polyline |
| DM | 姿态弧 h/v + RHD + dev-bottom 偏移 | ✅ |
| 模型 | Chevron 指标（距离/速度/TTC/全部） | ✅ `model_overlay` + `model_canvas` |
| 模型 | `allowThrottle` 路径淡化 | ✅ |
| 限速 | MUTCD 英制牌（SPEED/LIMIT 标签） | ✅ |
| 限速 | last/offset/超速红/无效灰/preActive 箭头/ahead | ✅ v47+ |
| 转向 | 转向灯/BSM 同位 + 参数门控 | ✅ v47 |
| Dev UI | BOTTOM=1 / RIGHT=2 / BOTH=3 枚举 | ✅ v48 修正告警/DM/扭矩偏移 |
| 扭矩 | 底栏 Dev UI 时 `bottom: 60px` | ✅ `hud_torque.js` |

---

## 关键缺口（仍为 🟡 或 ❌）

| 区域 | 项 | 状态 |
|------|-----|------|
| 告警 | full 尺寸动态高度 | ✅ v54 |
| Home | Prime 勾选纹理 | ✅ 色值对齐 `prime.py`（✓ #465bea / subscribed #86ff4e） |
| 侧栏 | Wi-Fi 分级纹理 | ✅ 圆点（与 `sidebar.py` 一致） |
| Steering | Torque 版本树 JSON | ✅ `/api/opui/steering/torque-versions` |
| 模型 | shader 级精度 | 🟡 canvas 近似 |
| 模型 | 车道线/彩虹路径实车 | 🟡 v53 已修，待上车验证 |
| i18n | 侧栏/dev 面板 | 🟡 dev 预设保留中文；静态 UI 已 i18n |

---

## 验证方式

```bash
# PC
py -3 webui/dev/run_pc.py --port 5080

# J3
python3.12 -m webui.webuid
```

1. 强刷 `?v=54`
2. Dev：严重告警 / onroad_engaged / long_only / alert_full / standstill_timer
3. 设置：软件下载状态中文「已是最新，最后检查：X分钟前」、巡航 SCC 中文标签、MADS 刹车踏板说明、变道 Road Edge 开关
4. Toggles 无左侧图标（SP 布局：开关左、标题右）
5. Home 顶栏 `sunnypilot` Audiowide + 版本号
6. 行车 WebRTC + 实验模式宽角切换 + DM 驾驶员画面
7. ChevronInfo 开启时前车指标淡入；英制下限速牌 MUTCD 样式

---

## v52 新增对齐项

| 区域 | 项 | 状态 |
|------|-----|------|
| Models | 选模型后 `needs_reset_cal` → Reset Calibration 确认 | ✅ |
| Models | Cancel Download 仅 `download_index` 存在时显示 | ✅ |
| Models | Clear cache 完整确认文案 + Clear Cache 按钮 | ✅ |
| Models | CameraOffset `custom_model_active` 门控 | ✅ |
| Models | offroad 时 Current Model 描述文案 | ✅ |
| Vehicle | Hyundai `multiple_button` Off/Dynamic/Predictive + 动态描述 | ✅ |
| SunnyLink | `required_consent_version` / `consent_declined_value` API | ✅ |
| Software | DisableUpdates 去重 confirm（仅 onBeforeChange 重启流） | ✅ |
| Device | Reset Calibration 确认文案 | ✅ |
| OSM | 删除中 `DELETING...`、Update 行 `done/total (%)` | ✅ |
| Network | Wi-Fi 连接中态 + 轮询至 connected | ✅ |
| Developer | Release/分支门控、互斥副作用 | ✅ |
| Steering | MADS limited param 同步、Torque 子面板门控 | ✅ |
| i18n | panels/app 加载与 SSH 硬编码中文清扫 | 🟡 侧栏/dev 面板仍有中文 |
| 竖屏 | `fitOpuiScale()` 旋转 90° 放大（v51） | ✅ |

</details>

---

## 变更记录

| 日期 | 内容 |
|------|------|
| 2026-08-14 | **v77**：WebGL path/lead 光晕、OSM 全量离线、侧栏 Wi-Fi 图标、扭矩 rAF、Dev 预设 |
| 2026-08-14 | **v76**：confidence ball、WebGL 车道光晕、OSM 磁盘缓存、Prime checkmark 贴图、mock 梯形车道 |
| 2026-08-14 | **v75**：`hud_circular.js` E2E 圆环 + 停车计时、OSM 内置离线包、`--dev-ui-adj` |
| 2026-08-14 | **v72**：合成告警 `alert_resolve.py`、MUTCD 圆角、转向灯滤波闪烁、DM 弧粗细/淡出；文档总览与缺口校正 |
| 2026-08-14 | **v71**：`speed_limit_mode`、DM `dm_snapshot`、Dev UI 4 项底栏、巡航圆角 0.35、overlay 流畅模式保留 |
| 2026-08-13 | v54：全屏告警 200/270 + 361/420、path_gradient/path_blend、侧栏/弹窗 i18n、bootstrap tr() |
| 2026-08-13 | v53：行车模型叠加修复 — 标定单例、path_polygon 彩虹路径、HTTP 轮询兜底、overlay 叠在视频上 |
| 2026-08-13 | v50：设置全面对齐 — 软件 i18n/Release Notes 折叠、巡航/MADS/变道标签与控件、模型名 fallback、子面板全宽返回 |
| 2026-08-13 | v49：SunnyLink 面板行序/赞助商/恢复按钮 primary |
| 2026-08-13 | v48：DM 人脸轮廓、Chevron 指标、MUTCD、Dev UI 枚举修正（合成告警至 v72 才实现） |
| 2026-08-13 | v47：转向灯/BSM/路名数据源、限速牌细化、DevUI 转向配色 |
| 2026-08-12 | P2/P3 收尾：Cruise/Visuals/Toggles/Trips/字体/Home 品牌、彩虹路径、Dev UI 告警偏移、WebRTC 全链路（v38） |
