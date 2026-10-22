# Carrot 端口服务：cp ↔ sp 逐项对照与补齐计划

目标：把 CarrotPilot（`E:/cp`）提供的**全部端口服务**在本仓库补齐，且**统一由 sunnypilot  
自己的控制链路承担**（`Params` 单一事实源 + cereal 取实时数据 + `CarrotServ` 单一入口 +  
manager 托管进程），而不是在 fork 里再长出一套并行控制面。

数据来源：`E:/cp/openpilot/selfdrive/carrot` 静态扫描 + 设备实测（2026-09-27）。

## 1. 端口总表

| 端口       | 协议        | 用途                   | cp    | sp          | 备注                                 |
| -------- | --------- | -------------------- | ----- | ----------- | ---------------------------------- |
| 7705     | UDP 出     | 设备发现广播               | ✅     | ✅           | 已实测在发（carrot_man + carrot_navi 双源） |
| 7706     | UDP       | 导航数据上行 + 监听          | ✅     | ✅           |                                    |
| 7709     | TCP       | 路线点                  | ✅     | ✅           |                                    |
| 7710     | ZMQ       | 远程控制命令               | ✅     | ✅           | `carrot_man` `bind tcp://*:7710`   |
| 7711     | TCP       | xiaoge 车辆/模型数据       | ✅     | ✅           | `xiaoge_data`                      |
| 7713     | HTTP      | navi 侧信道 / sinf      | ✅     | ✅           |                                    |
| 7714     | TCP/WS    | v2 navi              | ✅     | ✅           |                                    |
| 12345    | UDP       | kisa 限速直写            | ✅     | ✅           | `carrot_man._kisa_port`            |
| **7000** | HTTP + WS | **API 服务器（App 主通道）** | ✅     | **阶段 1 完成** | 参数 REST 已可用；`/ws/*` 待补             |
| **6999** | WS + PTY  | recovery 支持终端        | ✅     | ❌           | `recovery/server.py` 2,563 行       |
| 8082     | HTTP      | xiaoge V-ASM 页面      | ✅(外部) | ✅(V-ASM)    | ⚠️ 端点不同：缺 `/store_toggle_values`   |
| 8088     | HTTP      | 本 fork 自有 nav 参数面板   | —     | ✅           | fork 独有，非 cp 端口                    |

## 2. 7000 的路由面（cp 135 条，33 个文件，约 30,379 行）

| 文件                                                                                                       | 路由  | 归属                                                                          |
| -------------------------------------------------------------------------------------------------------- | --- | --------------------------------------------------------------------------- |
| `features/dashcam/*`（routes/replay/catalog/upload/…）                                                     | 30+ | 行车记录仪（回放、预览、下载、上传）                                                          |
| `features/params.py`                                                                                     | 13  | **参数 REST（已移植核心）**                                                          |
| `features/system.py`                                                                                     | 10  | 设备信息、网络、心跳、标定状态                                                             |
| `features/support_terminal.py` + `services/support_terminal.py`                                          | 13  | 支持终端（与 6999 配合）                                                             |
| `features/tools/*`                                                                                       | 17  | 工具页（git 状态、任务、设备信息）                                                         |
| `features/youtube_live*.py`（5 个文件）                                                                       | 40+ | YouTube 直播（含 H264/FLV/RTMP/字幕）                                              |
| `features/terminal.py`                                                                                   | 6   | 终端命令桥                                                                       |
| `features/setting_*(profiles/popular_values/favorites/unit_index/web_settings)`                          | 17  | 设置档案与目录                                                                     |
| `features/ws.py`                                                                                         | 4   | **`/ws/raw`、`/ws/raw_multiplex`、`/ws/compact_state`、`/ws/camera/{camera}`** |
| `features/carrot_navi/*`                                                                                 | 5   | v2 navi 桥与诊断                                                                |
| `features/{mapbox_tokens,screenrecord,egpu_model,bluetooth,ssh_keys,vision_*,xiaoge,cars,static,stream}` | 20+ | 其余功能页                                                                       |

配套：`realtime/` 1,610 行（8 个 py，含 C++/Cython 的 compact state）、`recovery/` 2,563 行。

**App（navipilot）实际只用 4 个端点**：  
`WS /ws/raw_multiplex?services=`、`WS /ws/camera/road`、`POST /api/param_set`、`GET /api/params_bulk`  
（另有 `POST http://<ip>:8082/store_toggle_values` 下发设置）。

## 3. 阶段计划

| 阶段    | 内容                                                                                                                              | 状态                                                                                        |
| ----- | ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **1** | `server/` 骨架 + `/api/param_set` `/api/params_bulk` `/api/health` + 托管进程 `carrot_server`                                         | ✅ 完成（24 tests，设备端到端实测通过）                                                                  |
| 2     | `/ws/raw_multiplex`（cp `realtime/raw_protocol.py` 37 + `raw_services.py` 45 + `transports/raw_ws.py` 325 + `features/ws.py` 99） | ✅ 完成（`features/ws.py` + `services/raw_protocol.py` / `raw_services.py` / `raw_relay.py`）  |
| 3     | `/ws/camera/{camera}`（`realtime/transports/camera_ws.py` 471）                                                                   | ✅ 完成（`features/camera.py` + `services/camera_relay.py`）                                   |
| 4     | `/ws/compact_state` 及原生部分（652 + C++/Cython）                                                                                     | ❌ 有意不实现：cp 的紧凑二进制 HUD 协议无 cereal 对应，猜一个会给出解码成错误数字的流；由 `features/unsupported.py` 回 501     |
| 5     | `features/system.py` + `features/cars.py` + `features/settings.py` 等只读设备/设置接口                                                   | ✅ 完成（`features/system.py` 9 路由、`cars.py`、`settings.py`、`preferences.py`、`credentials.py`） |
| 6     | dashcam / terminal / tools / youtube_live / support_terminal / recovery(6999)                                                   | ⏸️ 有意不实现，见 `features/unsupported.py` 的逐项理由（媒体子系统/无鉴权远程 shell/云直播）                         |
| 7     | 8082 补 `POST /store_toggle_values`                                                                                              | ✅ 完成（`VASMService.store_toggle_values` + v_asm_server 路由）                                 |

> 2026-09-28 复核：设备实测 7000/7706/7709/7710/7711/7712/7713/7714/12345/8082 全部在监听，>   
> 7705 广播正常发出。6999 与 8088 不在监听属预期（前者有意不实现，后者是 sp 自有面板未启用）。

## 3.1 明确不实现清单（有意为之，不是遗漏）

| 项                                                 | 理由                                           |
| ------------------------------------------------- | -------------------------------------------- |
| `/ws/compact_state`                               | Carrot Vision 的字节打包 HUD 协议在 sp 无对应 cereal 消息 |
| dashcam / screenrecord / replay                   | ~30 文件 ffmpeg 媒体子系统；sp 已有自己的路线存储与回放          |
| terminal / support_terminal                       | 7000 上的无鉴权远程 shell，同网段任何设备可执行车辆控制机上的命令       |
| youtube_live / vision_diag / vision_test          | 云直播与 Carrot Vision 上传/测试台                    |
| `/ws/carrot_navi/media`、`/stream`、`/ws/web_sound` | cp 自有 web HUD 的 fMP4/声音通道，sp 不跑该 HUD         |
| 6999 recovery 服务                                  | cp 的独立 PTY recovery 终端（2,563 行），同样是无鉴权 shell |

以上均由 `features/unsupported.py` 注册为 501（而不是留 404），让客户端能区分  
「本 fork 较旧」与「URL 写错了」。

## 3.2 cereal 模式差异（已知，需谨慎）

| 字段                                         | cp                        | sp                                       | 影响                                                                 |
| ------------------------------------------ | ------------------------- | ---------------------------------------- | ------------------------------------------------------------------ |
| `CarState.leftLatDist`                     | `@69`，hyundai carstate 写入 | **不存在**（sp 的 `@69` 是 `vehicleNaviSpeed`） | `xiaoge_data.collect_car_state` 用 `getattr(..., 0.0)` 兜底，不会崩；值恒为 0 |
| `ModelDataV2.MetaData.laneWidthLeft/Right` | 存在                        | **不存在**                                  | `xiaoge_vision.lane_width_meters` 已做容错；直接读会 AttributeError         |

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

> 注意：设备上跑这些测试要用 launcher 的真实 `PYTHONPATH`>   
> （`/data/openpilot:/usr/local/venv/lib/python3.12/site-packages:/data/.pydeps`），>   
> 否则 aiohttp 不在路径里、6 项会被静默跳过。

---

## 6. 7000 的 web 面板（cp `web/`）：为什么现在是 8088，以及能否照搬

> 2026-10-11 补。回答「cp 的面板不是 7000 吗，为什么我们是 8088；现在 7000 只回 JSON，>   
> 能不能直接照搬 cp 的 7000」。基准：cp = `E:/cp`（`carrot-wip`），sp = `E:/sp`（`test`）。

### 6.1 为什么 sp 是 8088 而不是 7000（根因）

三件事各归各位，不是端口写错：

| 事实                                      | 证据                                                                                                                                                                                                                                                                                   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| cp 的面板就是 7000，**面板与 API 同一进程**          | cp `server/app.py::make_app()` 末尾 `app.router.add_static("/", str(WEB_DIR), show_index=True)`，`WEB_DIR` = `selfdrive/carrot/web`；cp `selfdrive/ui/carrot_web.py:10` `CARROT_WEB_PORT = 7000`（UI 用二维码指向它）                                                                             |
| sp 只移植了 7000 的 **API 层**，前端 `web/` 从未移植 | sp `server/app.py::create_app()` 里没有任何 `add_static`，`/` 由 `_index()` 回一份 JSON 路由清单。本文档第 3 节的阶段 1–7 **全部是 API**，没有一项是 web 前端                                                                                                                                                          |
| sp 另建 8088 作为自己的面板，并把 UI 二维码改指 8088     | sp `selfdrive/ui/carrot_web.py:10` `CARROT_WEB_PORT = 8088  # matches CarrotWebEnabled's documented port`；`sunnypilot/carrot/web_interface.py`（stdlib `ThreadingHTTPServer`）由 `carrot_man.py:1295` 启动，受 `CarrotWebEnabled` 门控（默认 `"0"`）；`carrot_tuning.py:163` 的文案写的是 "on port 8088" |

补充：sp 的完整 web UI 在 **5080**（`webui/` 子模块，`launch_chffrplus.sh:781`  
`keep_alive webui webui/webuid.py 5080`，镜像大 UI 20 面板 + 18 子面板）。所以 sp 的分工是  
**7000 = App 的 JSON API / 8088 = carrot 小面板 / 5080 = 大 UI 镜像**；cp 只有 7000 一个。

⚠️ `openpilot/sunnypilot/carrot/README.md` 目前把 7000 整条列在「Not present」表里，**已过期**：  
`server/` 早已移植（sp 31 文件 / 5,399 行；cp 135 文件 / 27,499 行），且 `process_config.py:322`  
已托管 `carrot_server` 进程。**只有 `web/` 确实没有。**

### 6.2 「直接照搬」的可行性：静态层可以，页面级不行

**静态层（`web/` 目录）—— 可搬，成本低**

- `web/` = 566 文件 / 9.2 MB。`web/js/`、`web/css/` 的**构建产物已入库**：`web/.gitignore` 明写    
  *"Generated browser bundles are committed because the device serves this source tree directly    
  and does not run Node at startup"* → **设备端不需要 Node**。
- `index.html` 的 87 个绝对引用只落在 `/js`、`/css`、`/assets` 三个前缀，全在 `web/` 树内 →    
  `add_static("/", WEB_DIR)` 一条即可覆盖首屏。
- 落地所需：`server/config.py` 加 `WEB_DIR`（`SELFDRIVE_ASSETS_DIR` 对应的 `selfdrive/assets` sp 已有）、    
  `create_app()` 末尾加 `add_static("/shared-assets/", …)` + `add_static("/", WEB_DIR)`。
- 可选增强（cp 的 `features/static.py` 321 行 + `services/static_assets.py` 252 行 +    
  `services/asset_manifest.py` 210 行 + `services/web_capabilities.py`）：SHA-256 URL 指纹缓存、    
  启动预压缩、`__CARROT_BOOTSTRAP__` 注入。**不搬也能跑**：前端只在 10 个文件里读    
  `__CARROT_BOOTSTRAP__`，且 `index.html` 内联脚本对 `webSettings` 缺失有 try/catch 兜底 →    
  退化成「无缓存指纹、无能力门控」，页面照常打开。

**页面级 —— 不能整站照搬。** cp 前端调 57 个 `/api` 端点，在 sp 的落点：

| 结果           | 数量     | 说明                                                                                                                                                                                                                  |
| ------------ | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 有真实处理器       | **41** | 参数 / 设置 / 档案 / 收藏 / 热门值 / 单位索引 / intro / cars / egpu / bluetooth / carrot_navi / mapbox / ssh_keys / system …                                                                                                       |
| 只有 501（有意拒绝） | **14** | dashcam 5（`read-state`、`upload/{start,cancel,summary,test}`）、support_terminal 3（`{start,status,stop}`）、tools 3（`POST /api/tools`、`POST /api/tools/start`、`POST /api/tools/jobs/notice`）、vision_diag 2、vision_test 1 |
| 未注册          | **2**  | `/api/carrot_navi/client_diagnostic`（**唯一真实缺口**）；`/api/live_runtime{x}` 是查询串归一化的误报，sp 有 `/api/live_runtime`                                                                                                         |

WS 侧另有 `/ws/terminal`、`/ws/terminal_pty`、`/ws/compact_state`、`/ws/web_sound`、  
`/ws/carrot_navi/media`、`/stream` 全部 501。

按页面（依据 `web/js/generated/*.js` 的 API 依赖）折算：

| 页面                    | 依赖                                                                          | 照搬后                                                                                 |
| --------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `app.js`（壳）           | `/api/param_set`                                                            | ✅                                                                                   |
| `settings.js`         | favorites / popular_values / profiles / settings                            | ✅                                                                                   |
| `intro.js`            | intro / param_set / params_restore / web_settings                           | ✅                                                                                   |
| `drive.js`            | `/api/carrot_navi`、`/ws/carrot_navi`                                        | ⚠️ state 可用；media 通道 501                                                            |
| `tools.js`            | tools / dashcam / egpu / params_qr\_* / settings / bluetooth / web_settings | ⚠️ 只读部分可用；**`POST /api/tools` 与 `/api/tools/start` 是 501**，即「跑命令 / git reset」那半页不可用 |
| `logs.js`             | `/api/dashcam`、`/api/screenrecord`                                          | ❌ 全 501                                                                             |
| `terminal.js`         | `/ws/terminal`、`/ws/terminal_pty`                                           | ❌ 全 501                                                                             |
| `terminal-support.js` | `/api/support_terminal`                                                     | ❌ 全 501                                                                             |

### 6.3 为什么这 14+6 个不该为了「照搬面板」去补


`features/unsupported.py` 的模块 docstring 已逐项写明理由，其中两条是**安全底线**而非「还没做」：

- **terminal / support_terminal / tools 的写操作**：7000 上**没有任何鉴权**（cp 与 sp 的 server    
  都没有 auth/token 校验）。它就是「同网段任何人都能在控制车辆的那台计算机上执行命令」的入口；    
  cp 的 tools 页同理（`shell_cmd`、`git reset --hard`、`git sync`、`rebuild`）。
- **compact_state**：Carrot Vision 的字节打包 HUD 协议在 sp 无对应 cereal 消息，猜一个会得到    
  「解码成错误数字」的流。

所以照搬整站的净效果是：**新增 3 个完全不可用的页面 + 1 个半残页面，并制造「页面既然在，那把  
后端也补上」的压力**——而补的正是上面这两条，与 sp 现有安全决策直接冲突。

### 6.4 三个可选方案（待决策）

| 方案                   | 做法                                                                                                                                       | 代价                                   | 风险                            |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | ----------------------------- |
| **A. 不做**（维持现状）      | 7000 继续只做 App API；面板继续走 8088 / 5080                                                                                                      | 0                                    | 无                             |
| **B. 只搬「能用」的页面**（推荐） | 搬 `web/` 树 + `add_static`，但**摘掉** `logs` / `terminal` / `terminal-support` 三个页面的入口与 `tools` 页的命令区；补 `/api/carrot_navi/client_diagnostic` | 中（改 `index.html` 导航 + 3 个 bundle 入口） | 低（不引入无鉴权 shell）               |
| **C. 整站照搬**          | 原样搬 `web/` + 补齐 14 个 501 端点 + `/ws/terminal` 等                                                                                           | 大（cp `server/` 还有约 100 个文件未移植）       | **高**：引入无鉴权远程 shell / git 写操作 |

若选 B / C，必须同时处理：

1. **`/` 路由契约冲突**：`tests/test_carrot_server_completeness.py:296`     
   `test_the_index_lists_the_routes` 断言 `GET /` 返回带 `routes` 键的 JSON。让 `/` 改服 SPA 会打破它     
   → 需要把路由清单挪到 `/api/routes` 并同步改测试，且先确认伴生 App 不依赖 `GET /` 的 JSON。
2. **静态路由注册顺序**：`add_static("/")` 必须在所有显式路由（含 `unsupported.py` 的 `{tail:.*}`）之后注册，否则会遮蔽它们。
3. **`web/` 落点**：cp 在 `selfdrive/carrot/web`，sp 的 carrot 在 `sunnypilot/carrot/` → 建议     
   `openpilot/sunnypilot/carrot/web/`，并同步 `WEB_DIR`。
4. **版权**：cp 是纯 MIT；`web/` 是 cp 的构建产物，建议在该目录放一份来源说明。
5. **不要连带 `cweb_push.py`**：它是每 5 s 把设备 IP POST 到第三方中继的 phone-home agent     
   （URL 以 XOR 混淆内嵌），`carrot/README.md` 已把它标为「产品 / 隐私决策，不是移植任务」。

### 6.5 落地记录（2026-10-11）

先按 **B** 落地，随后用户改选 **C**：B 的「摘掉入口」全部回滚、501 端点全部补齐。下面是**最终状态**。

**7000 面板**

| 项 | 落地 |
|---|---|
| `web/` 树 | cp 的 `selfdrive/carrot/web` 逐字节复制到 `sunnypilot/carrot/web`（566 文件 / 9.2 MB）；构建产物已入库，设备不跑 Node |
| `config.py` | 新增 `BASE_DIR`/`ROOT_DIR`/`WEB_DIR`/`SELFDRIVE_ASSETS_DIR`/`TRAINING_ASSETS_DIR`/`OFFROAD_ASSETS_DIR`/`SOUND_ASSETS_DIR`/`DEFAULT_SETTINGS_PATH`，以及 dashcam / screenrecord / tmux / git-state 一组常量 |
| `app.py` | 按 cp 的 `features.register_all()` 顺序注册 **27 个 feature**，末尾 `add_static("/shared-assets/")` + `add_static("/", WEB_DIR)`；`GET /` 与 `/index.html` 由 `features/static.py::handle_index` 提供（注入 asset manifest / capabilities / web-settings）；原 `/` 的 JSON 路由清单在 `GET /api/routes` |
| `show_index` | **False**（cp 为 True）：面板不需要目录列表，开了会把 `web/src`、`web/tests` 暴露到局域网 |
| `unsupported.py` | 从 21 条拒绝缩到 **1 条**：只剩 `youtube_live`（cp 自己也不再提供） |

**`server/` 整树移植**

| 项 | 落地 |
|---|---|
| 规模 | cp 的 **99 个缺失文件**全部移植（`features/dashcam/` 25、`features/tools/` 5、`live_runtime/` 7、`terminal_commands/` 9、`services/` 23 等）；命名空间 `openpilot.selfdrive.carrot` → `openpilot.sunnypilot.carrot` |
| 基础模块 | `common/{async_process,repo_update,reboot}.py`、`selfdrive/car/openpilot_toggle.py`、`carrot/web_upload.py`、`carrot/realtime/`（`compact_state.py` 652 行 + `.pyx`/`.cc`/`.h`/`SConscript`，已接进 `sunnypilot/SConscript`） |
| **module/package 同名冲突** | `carrot_navi` / `tools` / `intro`：删 sp 的单文件、改用 cp 的包（cp 的 `carrot_navi/` 是超集，自带 `client_diagnostic`）；sp 独有的 `/api/regulatory` 移入 `system.py`，`/download/tmux.log` 由 cp 的 `terminal.py` 提供 |
| **同名不同 API 的 service** | `params.py` / `settings.py`：sp 版改名 `params_typed.py` / `settings_sp.py` 并重指 sp 的消费者，装 cp 版为规范；`device_info.py`：装 cp 版 + 追加 sp 的 `listening_ports` |
| 路径/API 重映射 | `openpilot.system.hardware` → `common.hardware`（**只改 cp 复制件**，sp 自有文件已回退以免改变其行为）；`openpilot.cereal.car` → `opendbc.car.structs.car`；`carrot.cruise_gap` → `sunnypilot.selfdrive.car.cruise_helpers` |
| `compact_state` | sp 的 `RawRelayHub` 增补 `is_compact_service` / `register_compact` / `_compact_frame`，复用 `compact_state.py` 编码；`compact_state_pyx` 可选（未编译时走纯 Python，线格式一致）；`/ws/compact_state` 由 `features/ws.py` 提供 |
| **未取（有意）** | `egpu_model.py`（sp 有自己的 `egpu.py`，读 chestnut/jetlink 而非 cp 的 `modeld/big_model` 管线）；两个 XOR 混淆 Discord webhook 与上传 relay **置空**；`carrot_settings.json`（189 KB，cp 前端设置页的元数据源）已复制 |
| 测试 | cp 的 `server/tests/` 移植 24 个（`test_egpu_model` 除外；`test_git_config` 整模块 skip——会真连远端）；sp 的契约测试按 cp 的实际行为更新（`web_language` 字段、intro 的 `shouldShow`、favorites 原样存、`known` 键等） |

**验证**

| 项 | 结果 |
|---|---|
| 路由 | **126 条**（原 96）；`GET /` 200 text/html；`/api/dashcam/*`、`/api/screenrecord/*`、`/api/vision_test/status`、`/api/terminal_pty/status`、`/api/support_terminal/status`、`/xiaoge` 全部 200；只有 `/api/youtube_live/*` 仍 501 |
| `ruff check openpilot` | **All checks passed**（cp 的 412 处自动修 + 36 条 per-file-ignores） |
| `compileall` | 干净 |
| carrot 测试 | **563 passed / 14 failed / 48 skipped**；那 14 项是桩件缺真 Params/cereal 的预存失败，已用 `git stash` 对比确认与本轮无关 |

> ⚠️ **安全提示（未变）**：7000 **依旧无鉴权**。C 方案把 cp 的终端、`/api/tools` 写操作、
> `support_terminal` 全部启用——同网段任何人都能在控车计算机上执行命令。若只要面板不要 shell，
> 回滚到 6.4 的 B 方案即可（改动集中在 `index.html` 与 3 个 JS 文件）。
