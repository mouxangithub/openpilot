# WebUI 测试：PC / 车机 / scrcpy

> 版本 `0.4.8` · 缓存 `?v=78`

---

## PC 预览（mock）

```bash
# 设置 WEBUI_DEV_PC=1（run_pc.py 已默认）
py -3 webui/dev/run_pc.py --port 5080
```

浏览器：`http://127.0.0.1:5080/?v=77`

| 项 | 说明 |
|----|------|
| Dev 预设 | 右下 Dev 面板或 `POST /api/opui/dev/preset/{name}` |
| 推荐预设 | `onroad_overlay`、`confidence_low`、`confidence_high`、`onroad_engaged` |
| op助手 | `webui_apply_dev_preset(preset=onroad_overlay)` |

**限制**：PC 为 mock overlay，**不能**替代 P0 真机标定。

---

## 车机

```bash
python3.12 -m webui.webuid --host 0.0.0.0 --port 5080
```

- 本机：`http://127.0.0.1:5080/?v=77`
- 局域网：`http://<tici-ip>:5080/?v=77`

健康检查：

```bash
curl -s http://127.0.0.1:5080/api/opui/bootstrap | head
curl -s "http://127.0.0.1:5080/api/opui/model/overlay?w=1600&h=900" | head
```

op助手：`webui_health_check(host=127.0.0.1, cache_bust=77)`

---

## scrcpy 对照

1. USB / Wi-Fi scrcpy 连接 C3
2. 并排：scrcpy 原生 UI + 浏览器 WebUI（同 engaged 状态）
3. 重点看 P0：车道、路径、前车
4. 记录偏差到 [VEHICLE_QA_CHECKLIST.md](VEHICLE_QA_CHECKLIST.md)

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 旧 UI / 无新功能 | 强刷 `?v=77`，清站点缓存 |
| `confidence_ball` 无数据 | 重启 Python（新 state_api） |
| 5080 被占用 | `webui_service_status` 查 PID，杀旧进程 |
| overlay 空 | 检查 onroad、`modeld`、WebRTC 权限 |

---

## 交接

- [OP_ASSISTANT_HANDOFF.md](OP_ASSISTANT_HANDOFF.md)
- [GUI_ALIGNMENT.md](GUI_ALIGNMENT.md)
