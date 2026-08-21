# Hermes Agent 借鉴 — 自我进化与平台备份（完整版）

参考：

- [hermes-agent](https://github.com/NousResearch/hermes-agent)
- [hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution)（DSPy + GEPA）

## 三层记忆（完整对标）

| 层级 | Hermes | op助手 | 状态 |
|------|--------|--------|------|
| L1 核心记忆 | SOUL / USER / MEMORY + **每日日志** | `workspace/*.md` + `workspace/memory/YYYY-MM-DD.md` + `ai_memory_notes` | ✅ |
| L2 程序记忆 | SKILL.md + progressive disclosure | `skills/registry.json` + **按需加载 Top-N** + `load_skill` 工具 | ✅ |
| L3 情景记忆 | SQLite FTS | `session_index.db` + `ai_web_sessions` + `search_past_conversations` | ✅ |

### Progressive Disclosure（按需披露）

- `skills/disclosure.py`：按用户 query、品牌、default_enabled 排序
- 固定注入：`safety-policy`、`memory-protocol`
- 默认最多加载 `ai_skills_disclosure_max`（设置 → 模型 → Hermes 进化闭环）
- 未加载技能以 manifest 列表呈现，AI 可 `load_skill(skill_id)` 拉取全文

## 闭环学习（Closed Learning Loop — 完整 5 步）

| 步骤 | Hermes | op助手 |
|------|--------|--------|
| 1 轨迹采集 | SQLite reasoning trace | ✅ `analyze_execution_traces` |
| 2 反思诊断 | GEPA + LLM | ✅ `evolution_reflect.reflect_on_trace`（JSON 根因 + 技能草案 + 工作区补丁） |
| 3 定向变异 | 改 SKILL / prompt / tool desc | ✅ 多候选 `generate_skill_variants` + `tool_desc_store` |
| 4 多候选评估 | Pareto 前沿 | ✅ `skill_evaluation.pareto_frontier` / `pick_best_candidate` |
| 5 人工门控 | PR 不自动 merge | ✅ `propose_learned_skill` → 平台批准；工具描述写入 overrides 可审计 |

### 自动管线

每次聊天结束（非 specialist 子任务）：

`evolution_pipeline.run_post_chat_pipeline`

1. 工作区稀疏 → `bootstrap_workspace_templates`（可关：`ai_evolution_auto_workspace`）
2. **对话提炼** → `memory_protocol.extract_and_persist_session_memory`（可关：`ai_evolution_auto_memory`，需 LLM）
3. 扫描热点轨迹
4. 可选自动技能提案（`ai_evolution_auto_propose`，默认关）
5. 可选工具描述进化（`ai_evolution_tool_desc`）

### 记忆协议（强依赖工具）

- 固定技能：`skills/memory-protocol/SKILL.md`（每轮 pinned）
- 对话中：**必须**调用 `append_daily_memory` / `update_workspace_file` / `update_agent_memory` 持久化
- 对话后：LLM 自动合并到当日日志 + MEMORY.md / USER.md 章节

手动：**设置 → 平台 → 技能进化** 或工具 `run_evolution_pipeline`。

## 配置（设置 → 模型 → Hermes 进化闭环）

| Param | 默认 | 说明 |
|-------|------|------|
| `ai_evolution_enabled` | 开 | 总开关 |
| `ai_evolution_auto_workspace` | 开 | 对话后补工作区骨架 |
| `ai_evolution_auto_memory` | 开 | 对话后 LLM 提炼每日日志 + MEMORY/USER |
| `ai_evolution_llm_reflect` | 开 | LLM 反思（需配置 API） |
| `ai_evolution_auto_propose` | 关 | 自动提案技能（仍须批准） |
| `ai_evolution_tool_desc` | 开 | 进化工具 description |
| `ai_skills_disclosure_max` | 10 | 每轮加载技能数上限 |
| `ai_evolution_candidates` | 3 | Pareto 候选数 |

## API

```
GET/POST /api/ai/platform/evolution?view=status|traces|pipeline
GET/POST /api/ai/platform/backup
GET/POST /api/ai/platform/workspace-health
GET/POST /api/ai/config  → evolution* 字段
```

## AI 工具

- `load_skill` — progressive disclosure 按需加载
- `analyze_execution_traces` / `evolve_skill_proposal` / `run_evolution_pipeline`
- `workspace_health` / `update_workspace_file` / `bootstrap_workspace`
- `append_daily_memory` / `read_daily_memory` / `list_daily_memory`
- `export_platform_backup` / `restore_platform_backup`
- `list_tool_desc_overrides`

## 与 Hermes 官方 GEPA 管线的差异

- **已内置** `ai/evolution/`：数据集 → 反思变异 → Pareto → 约束门 → 人工批准（无需克隆外部仓库）
- **可选 DSPy**：设置 `ai_evolution_use_dspy=1` 且 `pip install dspy` 时走官方 GEPA/MIPROv2 后端
- 车机默认 **API 原生 GEPA 循环**（3 轮、session 轨迹作 eval），成本可控
- Pareto 评分为启发式 + 可选 LLM judge，非完整 rollout benchmark

## 内置 GEPA API

```
POST /api/ai/platform/evolution
  {"operation":"gepa","skill_id":"memory-protocol","eval_source":"sessiondb"}
  {"operation":"gepa","status":true}   # 引擎状态
  {"operation":"gepa","dry_run":true,"skill_id":"sp-tuning"}
```

| Param | 默认 | 说明 |
|-------|------|------|
| `ai_evolution_gepa_enabled` | 开 | `evolve_skill_proposal` 优先走 GEPA |
| `ai_evolution_gepa_iterations` | 3 | 反思变异轮数 |
| `ai_evolution_eval_cases` | 8 | 评测用例数 |
| `ai_evolution_use_dspy` | 关 | 启用外部 DSPy GEPA（PC 开发机） |

Golden 数据集：`ai/evolution/datasets/<skill_id>/golden.jsonl`

已覆盖高频技能（共 35 条 golden）：`memory-protocol`、`sp-tuning`、`engage-troubleshooting`、`longitudinal-tuning`、`vehicle-adaptation`、`health-check`、`post-tune-validation`。详见 `evolution/datasets/README.md` 与 Wiki [GEPA-Evolution](https://github.com/mouxangithub/ai/wiki/GEPA-Evolution)。

## 推荐运维

1. 开启 **LLM 反思** + 关闭 **自动提案**（手动批准更安全）
2. 每周 **平台备份**
3. 重复失败流程：**扫描轨迹 → 生成进化提案 → 批准技能**
4. 长对话后检查工作区健康，或依赖自动 bootstrap + AI `update_workspace_file`
