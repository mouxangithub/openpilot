# 安装与集成

> 仓库：https://github.com/mouxangithub/ai  
> 路径：`<openpilot>/ai`

## 一键安装

**Comma 设备（默认 `/data/openpilot`）：**

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
```

**PC：**

```bash
export OPENPILOT_ROOT=/path/to/your/openpilot
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
```

## 安装脚本做什么

| 步骤 | 说明 |
|------|------|
| 1. 检测 `ai/` | 见下文「已有 ai 目录」 |
| 2. Git | 克隆或 `git pull` 到 `$OPENPILOT_ROOT/ai` |
| 3. **ai 配置** | `ai_*` 写入 `/data/ai/config.json`，**不修改** `params_keys.h`，无需编译 |
| 4. **可选 fork Param** | 若缺失则补齐 `SpDevBeep`（beepd 蜂鸣，需已编译进 `libparams_c.so` 或旧版 `params_pyx.so`） |
| 5. **自动改写 `launch_chffrplus.sh`** | 若无 `start_op_assistant`，注入启动 `ai.aid` 的函数与看门狗 |

以上第 3–5 步由 `install/integrate_openpilot.py` 执行，**每次安装/更新后都会跑一遍**（默认 `--skip-compile`）。

预编译 fork 无 SConstruct 也可安装：只要已有 `libparams_c.so`（新 sunnypilot）或 `params_pyx.so`（旧 fork）即可读写 openpilot 调参项；`ai_*` 不依赖编译。

## 已有 `ai/` 目录时怎么办

| 情况 | 安装脚本行为 |
|------|----------------|
| **不存在** `ai/` | 全新 `git clone` |
| **存在且为 git 仓库**（`ai/.git`） | 自动 `git pull` 更新，不删你的本地数据 |
| **存在但非 git**（例如主仓自带的拷贝） | 整目录备份为 `ai.bak.<时间戳>`，再重新 clone |

因此重复执行一键安装是安全的：git 安装会更新代码并重新 integrate；非 git 会先备份再覆盖。

## 更新

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/update.sh | bash
```

或 Web：**设置 → 开发 → op助手 版本 → 立即更新**（`git pull` + integrate）。

## 卸载

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/uninstall.sh | bash
# 或
bash /data/openpilot/ai/install/uninstall.sh
```

| 选项 | 作用 |
|------|------|
| （默认） | 停止 `ai.aid`，删除 `ai/` 目录 |
| `--restore-integrate` | 额外尝试用最新 `.bak` 恢复 `params_keys.h` / `launch_chffrplus.sh` |
| `--keep-local-data` | 删除前把 fork 分析/草稿备份到 `<openpilot>/.op-ai-local-backup/` |
| `--yes` | 跳过确认 |

**不会自动删除：** `/data/ai/config.json`（或 PC 上的 `AI_CONFIG_PATH` / `~/.comma/ai/config.json`）里的 `ai_*` 配置；openpilot 根目录下的 workspace、`ai_*` 数据文件（见下文）。

## 更新/卸载与用户数据 {#user-data-persistence}

op助手 的用户数据分三层存放。**正常 `git pull` 只更新 `ai/` 里被 git 跟踪的代码**，不会覆盖未跟踪的本地文件；真正需要当心的是「非 git 重装 `ai/`」和「卸载」。

### 各场景会丢什么、留什么

| 操作 | 会更新/删除 | 通常保留 |
|------|-------------|----------|
| op助手 **`git pull`**（Web「立即更新」或 `update.sh`） | `ai/` 内已跟踪源码；`integrate` 可能改写 `launch_chffrplus.sh` | 配置、`ai/data/`、缓存、fork 草稿、openpilot 根目录数据 |
| openpilot **主仓 `git pull`** | 主仓跟踪文件 | `/data/ai/config.json`；未提交的 `workspace/`、`ai_*` 等 |
| **`ai/` 非 git 安装**（无 `ai/.git`） | 旧 `ai/` 备份为 `ai.bak.<时间戳>` 后整目录重新 clone | 备份目录里的旧 `ai/`；车机 `/data/ai/config.json` |
| **`uninstall.sh`** | 删除整个 `ai/` | `/data/ai/config.json`；`<openpilot>/workspace/`、`<openpilot>/ai_tune_passport.jsonl` 等 |

### 数据存放位置

#### 1. `ai_*` 配置（API Key、模型、技能开关等）

存在 **git 仓库外**，更新 integrate **不会清空**已有内容：

| 环境 | 默认路径 |
|------|----------|
| Comma 车机 | `/data/ai/config.json` |
| PC | `~/.comma/ai/config.json`，或开发时 `<openpilot>/ai/data/user/config.json` |

可用环境变量固定路径（换 openpilot 目录也不丢）：

```bash
export AI_CONFIG_PATH=/data/ai/config.json   # 任意可写路径
export OPENPILOT_ROOT=/data/openpilot
```

#### 2. `ai/` 目录内本地数据（`ai/.gitignore` 已忽略）

| 路径 | 内容 |
|------|------|
| `ai/data/fork_analysis/latest.json` | Fork 分析报告缓存 |
| `ai/data/fork_drafts/<slug>/` | 技能/工具说明草稿 |
| `ai/cabana_cache/` | Cabana 解码缓存 |
| `ai/data/` | 其它本地数据 |
| `ai/config.json` | PC 开发用配置（若未设 `AI_CONFIG_PATH`） |

`git pull` **不会覆盖**上述目录。卸载时随 `ai/` 删除；可用 `uninstall.sh --keep-local-data` 先把 fork 分析/草稿备份到 `<openpilot>/.op-ai-local-backup/`。

草稿 **不会自动合并** 进 `ai/skills/` 正式技能，需人工审核后复制。

#### 3. openpilot 根目录下的工作区数据

由 `ai/system/paths.py` 的 `workspace_path()` 解析，路径在 **`<openpilot>/` 根下**，不在 `ai/` 子目录内：

| 路径 | 内容 |
|------|------|
| `workspace/USER.md`、`MEMORY.md`、`SOUL.md` 等 | 用户画像与人设（设置 → 平台可编辑） |
| `ai_tune_passport.jsonl` | 调参护照 |
| `ai_rag_vectors.json`、`ai_memory_vectors.json` | RAG / 记忆向量索引 |
| `adaptation_drafts/` | 适配草稿 |
| `ai_tune_snapshots/` | 调参快照 |
| `ai_audit_trail.jsonl`、`ai_notifications.json` | 审计与通知 |

更新 op助手 **不动**这些文件；卸载 op助手 **也不删**这些文件。

若你维护 openpilot fork，建议在主仓 `.gitignore` 中忽略用户数据，避免误提交：

```gitignore
prebuilt
ai_*
workspace/
adaptation_drafts/
```

（`prebuilt` 是构建产物，与 AI 用户数据无关；`ai_*` 可覆盖根目录下 `ai_tune_passport.jsonl` 等文件名。）

### `.gitignore` 能做什么、不能做什么

| 能做 | 不能做 |
|------|--------|
| 防止用户数据被 `git commit` | 防止 `rm -rf ai/`（卸载） |
| 让 `git pull` 不碰未跟踪文件 | 防止「非 git 安装 → 整目录替换」 |
| 区分代码与用户数据 | 替代定期备份 |

### 推荐备份（车机示例）

换机、大版本升级或 fork 切换前，可打包：

```bash
tar czf /data/ai-backup-$(date +%Y%m%d).tar.gz \
  /data/ai/config.json \
  /data/openpilot/workspace \
  /data/openpilot/ai_tune_passport.jsonl \
  /data/openpilot/ai/data
```

### 其它保持数据的方式

1. **始终用 git 安装 op助手** — 确认存在 `ai/.git`，更新走 `git pull` 而非手动覆盖目录。
2. **`AI_CONFIG_PATH` + `OPENPILOT_ROOT`** — 把配置与数据根固定到稳定路径。
3. **卸载前 `--keep-local-data`** — 备份 `ai/data/fork_*`。
4. **软链接（进阶）** — 例如将 `ai/data` 链到 `/data/op-ai-data`，换 openpilot 树时只改链接。

openpilot 主仓的 `launch_chffrplus.sh` / `params_keys.h` 补丁在 integrate 时写入；卸载默认**不还原**（除非 `--restore-integrate`）。

## 社区 Fork 与设备（C2 / C3 / 各社区分支）

安装/integrate 后会自动扫描当前 openpilot 树，写入 `<openpilot>/ai_install_snapshot.json` 与 `workspace/FORK_PROFILE.md`。若匹配到带 `wiki_repos` 的社区，会从 GitHub、Discourse 论坛或 MediaWiki 拉取文档进 RAG（需网络）。

```bash
# 手动同步当前 fork 的社区 Wiki
curl -X POST http://127.0.0.1:5090/api/ai/rag \
  -H 'Content-Type: application/json' \
  -d '{"operation":"wiki_ingest","max_files_per_repo":45}'
```

或在对话中让 AI 调用工具 `sync_community_wiki`（`confirm=true`）。

详见 [FORK_AND_COMMUNITY.md](FORK_AND_COMMUNITY.md)。

## 首次使用

打开 `http://<IP>:5090`，未完成配置时会弹出**首次向导**。也可在 **设置 → 模型** 配置。

## Fork 分析（不限定社区）

1. `GET /api/ai/fork/detect` — 扫描仓库  
2. `POST /api/ai/fork/analyze` — AI 阅读项目并写 `fork_analysis/latest.json`  
3. `POST /api/ai/fork/sync` — 生成 `fork_drafts/` 草稿  

开发面板：**设置 → 开发 → Fork 分析**。

## 手动集成

```bash
cd "$OPENPILOT_ROOT"
PYTHONPATH=$PWD python3 ai/install/integrate_openpilot.py --root "$PWD" --skip-compile
```

## 相关 API

| API | 说明 |
|-----|------|
| `GET /api/ai/package/version` | 版本 |
| `POST /api/ai/package/update` | 更新 + integrate |
| `POST /api/ai/integrate` | 仅重新 integrate |
