# GEPA Golden 评测集

供 `run_gepa_evolution` / `evolve_skill_proposal` 的 `eval_source=golden` 使用。

## 目录结构

```
datasets/
├── <skill_id>/
│   └── golden.jsonl    # 每行一条 EvalExample JSON
└── README.md
```

## 已覆盖高频技能

| skill_id | 场景 |
|----------|------|
| `memory-protocol` | 记忆、每日日志、USER/MEMORY |
| `sp-tuning` | 横向/纵向/MADS 调参 |
| `engage-troubleshooting` | 无法 Engage、Panda、SecOC |
| `longitudinal-tuning` | 跟车、加减速手感 |
| `vehicle-adaptation` | 新车指纹、适配草稿 |
| `health-check` | 一键体检、OTA 预检 |
| `post-tune-validation` | 改参后 A/B、快照回滚 |

## 字段

```json
{
  "task_input": "用户原话",
  "expected_behavior": "评判 rubric（好回答应做什么）",
  "difficulty": "easy|medium|hard",
  "category": "分类",
  "source": "golden"
}
```

## 用法

```bash
# API
POST /api/ai/platform/evolution
{"operation":"gepa","skill_id":"engage-troubleshooting","eval_source":"golden"}

# 工具
run_gepa_evolution(skill_id="sp-tuning", eval_source="golden")
```

维护：改 `golden.jsonl` 后走 PR；车机可随 `ai/` 更新同步。
