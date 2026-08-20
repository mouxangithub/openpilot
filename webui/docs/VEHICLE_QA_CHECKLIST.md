# WebUI 上车验收清单

> 强刷 `?v=77` · 对照 scrcpy 原生 BIG UI  
> P0 必须上车；P1/P2 可在 PC mock 预检但上车仍建议复核

---

## P0 — Overlay（必须真机）

- [ ] 车道线位置与曲率与 scrcpy 一致（无整体偏移 / 镜像）
- [ ] 彩虹路径中心线与车道几何匹配
- [ ] 前车 chevron 出现在 lead 车辆位置（有 lead 时）
- [ ] 无 overlay 时（mock/弱网）有合理降级，不白屏
- [ ] WebGL 与 Canvas fallback 至少一种正常

## P1 — 行车 HUD

- [ ] engaged / disengaged / override / lat_only / long_only 状态文案正确
- [ ] 速度单位与车机 Params 一致（mph / kmh）
- [ ] 扭矩条随 `torque_utilization` 平滑（rAF）
- [ ] 置信度球（mici）右缘显示与颜色渐变
- [ ] E2E 绿灯 / 前车驶离 / STOPPED 计时
- [ ] 告警条 small / mid / full 布局无裁切
- [ ] Developer UI 偏移不挡关键 HUD

## P2 — 离路 / 设置

- [ ] Home：Prime ✓、UPDATE pill、offroad alerts
- [ ] 侧栏：Wi-Fi 分级图标、蜂窝 / 热点状态
- [ ] 设置 15 面板可打开、保存 Params 生效
- [ ] OSM 区域列表（离线包 `full` 标记）
- [ ] 语言切换关键文案无截断

## 报告

- [ ] 记录：日期、设备、分支、`webui/VERSION`、浏览器 `?v=`
- [ ] P0 pass / fail 附 scrcpy 截图说明
- [ ] 使用 `webui_report_template` 输出给开发者
