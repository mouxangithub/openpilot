# Carrot 端口服务：cp ↔ sp 逐项对照与补齐计划

目标：把 CarrotPilot（`E:/cp`）提供的**全部端口服务**在本仓库补齐，且**统一由 sunnypilot
自己的控制链路承担**（`Params` 单一事实源 + cereal 取实时数据 + `CarrotServ` 单一入口 +
manager 托管进程），而不是在 fork 里再长出一套并行控制面。

数据来源：`E:/cp/openpilot/selfdrive/carrot` 静态扫描 + 设备实测（2026-09-27）。

## 1. 端口总表

| 端口 | 协议 | 用途 | cp | sp | 备注 |
|---|---|---|---|---|---|
| 7705 | UDP 出 | 设备发现广播 | ✅ | ✅ | 已实测在发（carrot_man + carrot_navi 双源） |
| 7706 | UDP | 导航数据上行 + 监听 | ✅ | ✅ | |
| 7709 | TCP | 路线点 | ✅ | ✅ | |
| 7710 | ZMQ | 远程控制命令 | ✅ | ✅ | `carrot_man` `bind tcp://*:7710` |
| 7711 | TCP | xiaoge 车辆/模型数据 | ✅ | ✅ | `xiaoge_data` |
| 7713 | HTTP | navi 侧信道 / sinf | ✅ | ✅ | |
| 7714 | TCP/WS | v2 navi | ✅ | ✅ | |
| 12345 | UDP | kisa 限速直写 | ✅ | ✅ | `carrot_man._kisa_port` |
| **7000** | HTTP + WS | **API 服务器（App 主通道）** | ✅ | **阶段 1 完成** | 参数 REST 已可用；`/ws/*` 待补 |
| **6999** | WS + PTY | recovery 支持终端 | ✅ | ❌ | `recovery/server.py` 2,563 行 |
| 8082 | HTTP | xiaoge V-ASM 页面 | ✅(外部) | ✅(V-ASM) | ⚠️ 端点不同：缺 `/store_toggle_values` |
| 8088 | HTTP | 本 fork 自有 nav 参数面板 | — | ✅ | fork 独有，非 cp 端口 |

## 2. 7000 的路由面（cp 135 条，33 个文件，约 30,379 行）

| 文件 | 路由 | 归属 |
|---|---|---|
| `features/dashcam/*`（routes/replay/catalog/upload/…） | 30+ | 行车记录仪（回放、预览、下载、上传） |
| `features/params.py` | 13 | **参数 REST（已移植核心）** |
| `features/system.py` | 10 | 设备信息、网络、心跳、标定状态 |
| `features/support_terminal.py` + `services/support_terminal.py` | 13 | 支持终端（与 6999 配合） |
| `features/tools/*` | 17 | 工具页（git 状态、任务、设备信息） |
| `features/youtube_live*.py`（5 个文件） | 40+ | YouTube 直播（含 H264/FLV/RTMP/字幕） |
| `features/terminal.py` | 6 | 终端命令桥 |
| `features/setting_*(profiles/popular_values/favorites/unit_index/web_settings)` | 17 | 设置档案与目录 |
| `features/ws.py` | 4 | **`/ws/raw`、`/ws/raw_multiplex`、`/ws/compact_state`、`/ws/camera/{camera}`** |
| `features/carrot_navi/*` | 5 | v2 navi 桥与诊断 |
| `features/{mapbox_tokens,screenrecord,egpu_model,bluetooth,ssh_keys,vision_*,xiaoge,cars,static,stream}` | 20+ | 其余功能页 |

配套：`realtime/` 1,610 行（8 个 py，含 C++/Cython 的 compact state）、`recovery/` 2,563 行。

**App（navipilot）实际只用 4 个端点**：
`WS /ws/raw_multiplex?services=`、`WS /ws/camera/road`、`POST /api/param_set`、`GET /api/params_bulk`
（另有 `POST http://<ip>:8082/store_toggle_values` 下发设置）。

## 3. 阶段计划

| 阶段 | 内容 | 状态 |
|---|---|---|
| **1** | `server/` 骨架 + `/api/param_set` `/api/params_bulk` `/api/health` + 托管进程 `carrot_server` | ✅ 完成（24 tests，设备端到端实测通过） |
| 2 | `/ws/raw_multiplex`（cp `realtime/raw_protocol.py` 37 + `raw_services.py` 45 + `transports/raw_ws.py` 325 + `features/ws.py` 99） | ✅ 完成（`features/ws.py` + `services/raw_protocol.py` / `raw_services.py` / `raw_relay.py`） |
| 3 | `/ws/camera/{camera}`（`realtime/transports/camera_ws.py` 471） | ✅ 完成（`features/camera.py` + `services/camera_relay.py`） |
| 4 | `/ws/compact_state` 及原生部分（652 + C++/Cython） | ❌ 有意不实现：cp 的紧凑二进制 HUD 协议无 cereal 对应，猜一个会给出解码成错误数字的流；由 `features/unsupported.py` 回 501 |
| 5 | `features/system.py` + `features/cars.py` + `features/settings.py` 等只读设备/设置接口 | ✅ 完成（`features/system.py` 9 路由、`cars.py`、`settings.py`、`preferences.py`、`credentials.py`） |
| 6 | dashcam / terminal / tools / youtube_live / support_terminal / recovery(6999) | ⏸️ 有意不实现，见 `features/unsupported.py` 的逐项理由（媒体子系统/无鉴权远程 shell/云直播） |
| 7 | 8082 补 `POST /store_toggle_values` | ✅ 完成（`VASMService.store_toggle_values` + v_asm_server 路由） |

> 2026-09-28 复核：设备实测 7000/7706/7709/7710/7711/7712/7713/7714/12345/8082 全部在监听，
> 7705 广播正常发出。6999 与 8088 不在监听属预期（前者有意不实现，后者是 sp 自有面板未启用）。

## 3.1 明确不实现清单（有意为之，不是遗漏）

| 项 | 理由 |
|---|---|
| `/ws/compact_state` | Carrot Vision 的字节打包 HUD 协议在 sp 无对应 cereal 消息 |
| dashcam / screenrecord / replay | ~30 文件 ffmpeg 媒体子系统；sp 已有自己的路线存储与回放 |
| terminal / support_terminal | 7000 上的无鉴权远程 shell，同网段任何设备可执行车辆控制机上的命令 |
| youtube_live / vision_diag / vision_test | 云直播与 Carrot Vision 上传/测试台 |
| `/ws/carrot_navi/media`、`/stream`、`/ws/web_sound` | cp 自有 web HUD 的 fMP4/声音通道，sp 不跑该 HUD |
| 6999 recovery 服务 | cp 的独立 PTY recovery 终端（2,563 行），同样是无鉴权 shell |

以上均由 `features/unsupported.py` 注册为 501（而不是留 404），让客户端能区分
「本 fork 较旧」与「URL 写错了」。

## 3.2 cereal 模式差异（已知，需谨慎）

| 字段 | cp | sp | 影响 |
|---|---|---|---|
| `CarState.leftLatDist` | `@69`，hyundai carstate 写入 | **不存在**（sp 的 `@69` 是 `vehicleNaviSpeed`） | `xiaoge_data.collect_car_state` 用 `getattr(..., 0.0)` 兜底，不会崩；值恒为 0 |
| `ModelDataV2.MetaData.laneWidthLeft/Right` | 存在 | **不存在** | `xiaoge_vision.lane_width_meters` 已做容错；直接读会 AttributeError |

补齐 `leftLatDist` 需要一个新的 ordinal（不能用 69），并同步 hyundai carstate 与
capnp 生成代码；属 schema 变更，需设备侧重新生成后再验证。

## 4. 统一控制原则（所有阶段共同遵守）

1. **状态只经 `Params`**：写参数一律用 `Params.put`，并在写前用 `Params.get_type()` 把
   值强制成声明类型——`put` 对类型不符是**抛 TypeError**，不是隐式转换（`OnroadUploads`
   那次就是这样踩到的）。写错类型返回 400 并带可读原因，绝不放成 500。
2. **实时数据只读 cereal**：WebSocket 流以 `SubMaster` 订阅现有服务，不新造数据面。
3. **不新增控制入口**：任何要改车行为的动作，最终都落到 `CarrotServ.update_raw` /
   `card.py` 单点写入，保持 `carState` 单写入者。
4. **进程由 manager 托管**：`carrot_server` 注册为 `always_run`（`enabled=not
   CARROT_WEB_EXTERNAL`），崩溃可见、可回滚，不自己 daemon 化。
5. **核心可离线测试**：`services/params.py` 不导入原生 params（按类型名分派、`UnknownKeyName`
   有兜底），因此纯函数部分在任何机器都能跑；HTTP 层用 aiohttp test_utils 端到端跑。

## 5. 阶段 1 的实测证据（设备 192.168.2.246）

```
LISTEN 0 128 0.0.0.0:7000
GET  /api/health        -> {"ok": true, "status": "ok"}
GET  /api/params_bulk?names=IsMetric,CarrotEnabled,DefinitelyNotAKey
                        -> {"ok": true, "values": {"IsMetric": true, "CarrotEnabled": true, "DefinitelyNotAKey": null}}
POST /api/param_set {"name":"IsMetric","value":"oops"}
                        -> 400 {"ok": false, "error": "cannot read 'oops' as a boolean"}
POST /api/param_set {"name":"OnroadUploads","value":0}
                        -> {"ok": true, "name": "OnroadUploads", "value": false}
POST /api/param_set {"name":"CarParams","value":"x"}
                        -> 400 {"ok": false, "error": "CarParams is written by the device and is read-only over the API"}
POST /api/param_set {"name":"NopeKey","value":1}
                        -> 400 {"ok": false, "error": "unknown parameter NopeKey"}
```

单测：本地 18 通过 / 6 跳过（缺 aiohttp 与原生 params）；设备上 **24/24 通过**（含 6 项真实
aiohttp + 真实 Params 的端到端）。

> 注意：设备上跑这些测试要用 launcher 的真实 `PYTHONPATH`
> （`/data/openpilot:/usr/local/venv/lib/python3.12/site-packages:/data/.pydeps`），
> 否则 aiohttp 不在路径里、6 项会被静默跳过。
