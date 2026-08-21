# Web UI vs 车机 raylib UI — 差距清单

**结论：功能与交互模式已高度对齐；像素级与 VisionIPC 渲染非 1:1。**

详细分项、占比与 Roadmap 见 **[GUI_ALIGNMENT.md](./GUI_ALIGNMENT.md)**（v74 起为唯一权威清单）。

## 三句话总结

1. **功能对齐 ~94%**：v71–v77 行车/设置补丁已基本覆盖（除上车验证项）。
2. **视觉对齐 ~85%**：WebGL2 + CSS/DOM 近似 raylib。
3. **不是 1:1**：VisionIPC / GPU shader 为架构差异。

## v0.4.8 / v78

边框 0.12、`onroad_fade` 底纹、SLA/SCC/E2E/ICBM 动效对齐、路沿 alpha、Home i18n、Web onboarding、op助手新工具。强刷 `?v=78`

## v0.4.7 / v77

WebGL path/lead 多层光晕、mock 前车、OSM **173 国 + 56 州**全量离线、侧栏 Wi-Fi 分级图标、扭矩 rAF、DM fade 滤波、`opui_coords` 触控映射、Dev 置信度/叠加预设。

车机：`python3.12 -m webui.webuid --port 5080`，强刷 `?v=77`

## v0.4.6 / v76

Confidence ball、WebGL 车道光晕、OSM 磁盘缓存、Prime `checkmark.png`、mock 梯形车道 polygon。

**原生 raylib 真画面投屏**（非 WebUI 范围）：见 [FUTURE_RAYLIB_UI_MIRROR.md](./FUTURE_RAYLIB_UI_MIRROR.md).
