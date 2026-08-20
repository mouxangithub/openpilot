# WebUI PC 开发与交接

## 何时使用

用户在 PC 开发 WebUI、需要 Dev 预设、健康检查、或交接上车测试前预检时启用。

## 步骤

1. `get_host_environment` — 确认 PC / 车机 / 无屏
2. `webui_package_info` — VERSION、`?v=78`
3. `webui_headless_status` — 无屏时确认 `effective_headless`
4. `webui_service_status` — :5080 是否监听
5. `webui_health_check(cache_bust=78)` — API 是否正常
6. `webui_list_dev_presets` — 可用 Dev 预设列表
7. PC only：`webui_apply_dev_preset(preset=onroad_overlay)` 等
8. `webui_onboarding_status` — 条款/训练是否完成
9. `webui_qa_checklist(scope=pc)` — PC 可测 v78 抛光项
10. 上车前指向 `webui-vehicle-qa` 与 `OP_ASSISTANT_HANDOFF.md`

无屏车机：见技能 `headless-webui` 与 `ai/docs/HEADLESS_WEBUI.md`。

## Dev 预设（PC）

| preset | 用途 |
|--------|------|
| `onroad_overlay` | 车道/路径/置信度/DevUI |
| `confidence_low` / `confidence_high` | 置信度球 |
| `onroad_engaged` | 一般 engaged HUD |
| `e2e_green` / `standstill_timer` | E2E 圆环 |

需 `WEBUI_DEV_PC=1`（`run_pc.py` 默认开启）。

## v78 PC 验证要点

- 边框圆角更圆（0.12）
- engaged + 扭矩条时底部 `onroad_fade` 纹理
- SLA preActive 箭头淡入、SCC 标签淡入
- Home UPDATE/ALERTS 中英文切换

## 启动命令

```bash
py -3 webui/dev/run_pc.py --port 5080
# http://127.0.0.1:5080/?v=78
```

## 相关

`webui/docs/TESTING_PC_DEVICE_SCRCPY.md`、`webui/docs/GUI_ALIGNMENT.md`
