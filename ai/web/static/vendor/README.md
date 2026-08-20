# 前端 vendor 依赖（离线可用）

与 xterm 相同：**全部随仓库提交**，车机无网也能用，安装脚本不再拉 CDN。

## Three.js（OP 办公室 3D）

已内置在仓库（`three@0.160.1`）：

| 文件 | 说明 |
|------|------|
| `three/three.module.js` | ES Module 主库（办公室场景使用） |
| `three/three.min.js` | UMD 备用 |
| `three/examples/jsm/loaders/GLTFLoader.js` | GLB 家具（可选） |
| `three/examples/jsm/utils/BufferGeometryUtils.js` | GLTFLoader 依赖 |
| `three/examples/jsm/controls/OrbitControls.js` | 旋转/缩放视角 |

**维护者升级版本**（需联网，在开发机执行后提交 git）：

```bash
VER=0.160.1
BASE=ai/web/static/vendor/three
curl -fsSL "https://cdn.jsdelivr.net/npm/three@${VER}/build/three.module.js" -o "$BASE/three.module.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/three@${VER}/build/three.min.js" -o "$BASE/three.min.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/three@${VER}/examples/jsm/loaders/GLTFLoader.js" -o "$BASE/examples/jsm/loaders/GLTFLoader.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/three@${VER}/examples/jsm/utils/BufferGeometryUtils.js" -o "$BASE/examples/jsm/utils/BufferGeometryUtils.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/three@${VER}/examples/jsm/controls/OrbitControls.js" -o "$BASE/examples/jsm/controls/OrbitControls.js"
```

## 办公室 GLB（Kenney CC0）

`office/manifest.json` v3 列出 **家具 / 道路 / 赛车** 三套 Kenney 模型（已随仓库提交）。场景在 `office-scene-3d.mjs` 中优先加载 GLB，失败时回退程序化几何体。

| 套件 | 用途 |
|------|------|
| furniture-kit | 工位（桌/椅/显示器）、茶水间、休息区、书柜 |
| city-kit-roads | 中心车道、十字路口、路障、锥桶、路灯 |
| racing-kit | Replay 跑道、赛车、旗子、红绿灯（Engage 区） |

**从 Kenney 官网重新导入**（开发机执行后提交 git）：

```bash
# 1. 将三个 zip 解压到 _staging
#    ai/web/static/vendor/office/_staging/{furniture,roads,racing}
# 2. 复制精选 GLB 到 office/
node ai/scripts/import_kenney_office.mjs
```

许可文件：`office/LICENSE-furniture.txt`、`LICENSE-roads.txt`、`LICENSE-racing.txt`

暂存目录 `_staging/` 仅本地解压用，不必提交。

### 已导入模型（23 个）

| 套件 | 模型 |
|------|------|
| furniture-kit | desk, chair, monitor, sofa, plant, coffee-table, coffee-machine, bookcase |
| city-kit-roads | road-straight/bend/crossroad/crossroad-path/end, barrier, cone, street-light |
| racing-kit | track-straight/corner/start, vehicle-sedan, race-barrier, flag-checkers, traffic-light |
| mini-characters | character-male-a~f, character-female-a~f（专员骨骼动画） |

场景加载时会**自动归一化**：底面对齐地面、XZ 居中、按 `footprint` 缩放到统一尺寸（道路瓦片 1.0m）。人物模型按 `height: 0.95` 缩放到约 1m 高，并播放 idle / walk / sit 动画。

### 同一套 zip 里还可加（无需新下载）

解压后在 `_staging` 里找到以下 GLB，可扩展 `import_kenney_office.mjs` 的 `PICKS`：

**furniture-kit**（`Models/GLTF format/`）：
- `computerKeyboard.glb` — 键盘
- `lampRoundTable.glb` / `lampSquareTable.glb` — 台灯
- `trash.glb` — 垃圾桶
- `wall.glb` / `wallDoorway.glb` — 隔断墙
- `rugRound.glb` / `rugRectangle.glb` — 地毯
- `bookcaseOpen.glb` — 开放书架
- `kitchenFridge.glb` — 冰箱（茶水间）

**city-kit-roads**（`Models/GLB format/`）：
- `road-intersection.glb` — T 字路口
- `sign-highway.glb` / `sign-highway-detour.glb` — 路牌
- `light-curved.glb` — 弯道路灯

**racing-kit**（`Models/GLTF format/`）：
- `raceCarGreen.glb` / `raceCarBlue.glb` — 更多车辆
- `arch.glb` / `grandstand.glb` — Replay 区装饰
- `lightGreen.glb` — 绿灯

### 官方下载（手动）

若 zip 丢失，从 Kenney 官网下载 CC0 包：

1. [Furniture Kit](https://kenney.nl/assets/furniture-kit) → `kenney_furniture-kit.zip`
2. [City Kit Roads](https://kenney.nl/assets/city-kit-roads) → `kenney_city-kit-roads.zip`
3. [Racing Kit](https://kenney.nl/assets/racing-kit) → `kenney_racing-kit.zip`
4. [Mini Characters 1](https://kenney.nl/assets/mini-characters) → `kenney_mini-characters.zip`

解压到 `ai/web/static/vendor/office/_staging/{furniture,roads,racing,characters}` 后运行 `node ai/scripts/import_kenney_office.mjs`。

### 可选第四套（增强办公室感）

- [Office Kit](https://kenney.nl/assets/office-kit) — 文件柜、会议桌等（若页面存在）
- [Computer Kit](https://kenney.nl/assets/computer-kit) — 更多 PC 外设

## xterm（Web 终端）

| 文件 | 来源 |
|------|------|
| `xterm/xterm.js` | @xterm/xterm@5.5.0 |
| `xterm/xterm.css` | @xterm/xterm@5.5.0 |
| `xterm/addon-fit.js` | @xterm/addon-fit@0.10.0 |

更新：

```bash
cd ai/web/static/vendor/xterm
npm pack @xterm/xterm@5.5.0 @xterm/addon-fit@0.10.0
tar -xzf xterm-xterm-5.5.0.tgz && cp package/lib/xterm.js package/css/xterm.css .
tar -xzf xterm-addon-fit-0.10.0.tgz && cp package/lib/addon-fit.js .
rm -rf package *.tgz
```

引用见 `index.html` → `/static/vendor/...`

## markdown-it（聊天 Markdown，OpenClaw 对齐）

| 文件 | 说明 |
|------|------|
| `markdown-it/markdown-it-tasklists.bundle.js` | markdown-it@14.3.0 + task-lists（esbuild 打包） |
| `markdown-it/purify.min.js` | DOMPurify@3.x HTML 消毒 |
| `markdown-it/highlight.min.js` | highlight.js@11.11.1 代码高亮 |
| `markdown-it/highlight-github-dark.min.css` | 代码块主题 |

页面加载顺序（`index.html`）：bundle → purify → highlight → `js/markdown.js`。

**维护者重建 bundle**（开发机，需 Node）：

```bash
cd ai/web/static/vendor/markdown-it
npm install markdown-it@14.3.0 markdown-it-task-lists@2.1.1 --no-save
npx esbuild build-entry.js --bundle --format=iife --global-name=OpMarkdown --outfile=markdown-it-tasklists.bundle.js --minify
```

更新 purify / highlight：

```bash
curl -fsSL "https://cdn.jsdelivr.net/npm/dompurify@3.2.4/dist/purify.min.js" -o purify.min.js
curl -fsSL "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/highlight.min.js" -o highlight.min.js
curl -fsSL "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/styles/github-dark.min.css" -o highlight-github-dark.min.css
```

