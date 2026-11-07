# PC 本地预览

在 **openpilot 根目录** 运行：

```bash
py -3 webui/dev/run_pc.py --port 5080
```

或（自动检测并启用 Mock）：

```bash
py -3 -m webui.webuid --host 127.0.0.1 --port 5080
```

浏览器打开 `http://127.0.0.1:5080/`，强刷缓存（`?v=55`）。

**Web UI 自更新（PC 模拟）**：在 `mock_runtime.SIM` 中设置 `webui_update_available: True` 可测试 **软件** 面板底部 Web UI 行与弹窗。

**GUI 对齐清单**（与原生 BIG UI 逐项对照）：[`docs/GUI_ALIGNMENT.md`](../docs/GUI_ALIGNMENT.md)

## 与 J3 车机的差异

| 项 | PC 预览 | J3 真机 |
|----|---------|---------|
| Params | 内存 Mock | `/data/params` |
| 行车状态 | Dev 面板模拟 | cereal SubMaster |
| 车型 | 默认 `TOYOTA_WILDLANDER_PHEV`（SIM） | `CarParamsPersistent` |
| 相机 | 无 WebRTC 流 | 设备相机 |
| 配对状态 | 默认未配对（可改 SIM.paired） | Prime / DongleId |

PC 仅用于 UI 布局与交互调试；发布前请在 J3 上验证。

## 黑屏排查

1. 确认终端无 `ImportError: ParamKeyType`（需最新 `mock_runtime.py`）
2. 必须用 `run_pc.py` 或 `webuid` 自动 Mock，不要裸跑未 patch 的 server
3. 浏览器 F12 → Console / Network：`/ws/opui` hello、`/api/opui/bootstrap` 应 `ok: true`
4. 若只见设置页灰框：点左侧 ✕ 回到首页，或检查 `/api/opui/panels/device`
