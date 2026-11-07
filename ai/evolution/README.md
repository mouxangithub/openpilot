# OP Agent 内置 GEPA 自进化

对标 [hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution)，**无需克隆外部仓库**即可在车机/PC 使用。

## 流程

```
加载技能 (registry SKILL.md)
    → 构建评测集 (session 轨迹 / synthetic / golden.jsonl)
    → 约束校验 (大小 / 增长 / 安全语义)
    → 反思变异循环 (GEPA) 或可选 DSPy.GEPA
    → Pareto 选优
    → propose_learned_skill（人工批准）
```

## 用法

### Web / API

```http
POST /api/ai/platform/evolution
{"operation":"gepa","skill_id":"memory-protocol","eval_source":"sessiondb"}

GET /api/ai/platform/evolution?view=status   # 含 gepa 引擎状态
```

### AI 工具

- `run_gepa_evolution` — 指定 `skill_id` 运行完整 GEPA
- `run_evolution_pipeline` — 轨迹 + GEPA + 记忆（手动）

### 设置

| Param | 默认 |
|-------|------|
| `ai_evolution_gepa_enabled` | 开 |
| `ai_evolution_gepa_iterations` | 3 |
| `ai_evolution_eval_cases` | 8 |
| `ai_evolution_use_dspy` | 关（PC 可 `pip install dspy` 后开启） |

## Golden 数据集

`ai/evolution/datasets/<skill_id>/golden.jsonl`

## Golden 数据集

`ai/evolution/datasets/<skill_id>/golden.jsonl` — 每行 JSON：`task_input`、`expected_behavior`、`difficulty`、`category`。

| skill_id | 用例数 | 场景 |
|----------|--------|------|
| memory-protocol | 5 | 记忆、偏好、跳过寒暄 |
| sp-tuning | 6 | 横向/纵向/MADS |
| engage-troubleshooting | 6 | Engage、Panda、SecOC、Lite |
| longitudinal-tuning | 5 | 跟车手感、验证 |
| vehicle-adaptation | 5 | 指纹、CAN、草稿 |
| health-check | 4 | 体检、OTA、进程 |
| post-tune-validation | 4 | A/B、快照、护照 |

索引：`evolution/datasets/README.md`；用户 Wiki：[GEPA-Evolution](wiki/GEPA-Evolution.md)。

`eval_source=golden` 时优先加载上述文件；无 golden 时回退 synthetic/session。

## 模块

| 文件 | 职责 |
|------|------|
| `gepa_engine.py` | 主编排 |
| `dataset.py` | 评测集 |
| `fitness.py` | LLM judge |
| `reflect_mutate.py` | 反思变异 |
| `constraints.py` | Hermes 护栏 |
| `dspy_backend.py` | 可选官方 DSPy |
