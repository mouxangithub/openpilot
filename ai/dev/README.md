# PC 本地预览

在 Windows / macOS / Linux 开发机上快速启动 Web UI（无需 AGNOS 编译环境）。

## 启动

在 **openpilot 根目录**执行：

```bash
py -3 ai/dev/run_pc.py
# 或指定端口
py -3 ai/dev/run_pc.py --port 5090 --host 127.0.0.1
```

浏览器打开：**http://127.0.0.1:5090/**

`run_pc.py` 会在 import `ai` 之前安装最小 `openpilot.*` mock（Params、swaglog），并设置 `AI_DEV_PC=1`。

## 限制

| 项 | PC 预览 | 车机 AGNOS |
|----|---------|------------|
| Params | Mock 内存字典 | 真实 `/data/params` |
| 车辆状态 | 无 cereal，状态为离线默认值 | 实时 vEgo / 点火等 |
| Web 终端 PTY | Windows 不可用（提示用 WSL） | bash PTY |
| TSK / SecOC | 缺 `pycryptodome` 时路由跳过 | 完整 |
| opendbc | 常不可用，Cabana DBC 503 | 完整 |
| 聊天 / 设置 / Canvas | 可用（需配置 API Key） | 完整 |

## 依赖

```bash
pip install aiohttp
# 可选：pip install pycryptodome   # 启用 TSK 路由
# 可选：pip install tzdata          # Windows 完整 IANA 时区（否则自动 UTC+8 回退）
```

## 验证

```bash
# 架构 import 门禁（脚本内自动 PC mock）
py -3 ai/scripts/verify_architecture.py

# 单元测试（需从 openpilot 根目录）
py -3 ai/tests/run_tests_pc.py

# 快速 API 自检
curl -s http://127.0.0.1:5090/api/ai/status
curl -s http://127.0.0.1:5090/api/ai/bootstrap?lite=1
```

部分单元测试（如 `test_config_store` 中真实 `Params` 写入）在纯 PC mock 下可能阻塞，属预期；完整回归请在车机或完整 openpilot venv 执行。

## 车机正式运行

```bash
cd /data/openpilot
python3 -m ai.aid --port 5090
```

或由 manager / `launch_chffrplus.sh` 拉起（见 `install/install.sh`）。

## 架构文档

- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [docs/ARCHITECTURE_TARGETS.md](../docs/ARCHITECTURE_TARGETS.md)
