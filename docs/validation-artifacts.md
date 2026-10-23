# 验证产物规范：`docs/*_validation.json`

> 目的：让"已验证"三个字可复算、可审计、可回滚。任何性能/行为对比结论（A/B、移植前后、调参前后）
> 都必须落一份 `docs/<topic>_validation.json`，没有产物文件的验证结论一律视为**未验证**。
> 配套阅读：根目录 `AGENTS-memory.md`（活的仓库记忆）。

## 文件命名

```
docs/<topic>_validation.json      # 例：docs/coasting_veto_validation.json
```

`<topic>` 用 kebab-case，与该验证涉及的守卫测试模块名保持可关联（如 `test_capnp_contract_guard.py` → `capnp_contract`）。

## Schema（v1）

```jsonc
{
  "schema_version": 1,
  "topic": "coasting_veto",                    // kebab-case，与文件名一致
  "generated_at": "2026-10-23T12:00:00+08:00", // ISO 8601，本地时区可读
  "generator": {                               // 谁跑的、怎么跑的
    "runner": "human | agent-<name> | unittest | process_replay",
    "command": "PYTHONPATH=E:\\sp python -m unittest openpilot.sunnypilot.carrot.tests.test_signal_enabled_since",
    "hostname": "pc-win | c3-<name>",
    "notes": "PC 侧；msgq.ipc_pyx 未编，仅静态+mock 验证"
  },
  "baseline_revision": "abc1234",              // 对照基线的 git SHA（必填！没有基线就没有 before/after）
  "subject_revision": "def5678",               // 被验证的改动所在 git SHA
  "claims": [                                  // 每条要证明的命题一个条目
    {
      "claim": "coasting 在 reset_state 时退出且不产生 thrust",
      "level": 3,                              // 证据等级 1-8（见下表）
      "method": "unit-test",
      "result": "pass",                        // pass | fail | skip（skip 必须给理由）
      "skip_reason": null,
      "evidence": {                            // 可复算的原始证据
        "test": "openpilot.sunnypilot.carrot.tests.test_signal_enabled_since",
        "tests_run": 3, "failures": 0, "errors": 0, "skipped": 0,
        "output_fingerprint": "sha256:..."     // 关键输出的哈希或摘要行
      }
    }
  ],
  "confusion_matrix": {                        // 有真值标签的检测/分类类验证必填，其余可 null
    "tp": 0, "fp": 0, "fn": 0, "tn": 0,
    "note": "例：观测有效性判定，人工标注 N 帧为真值"
  },
  "before_after": {                            // 性能/行为对比必填；单点验证可 null
    "metric": "frameDropPerc",                 // 指标名（⚠️ 用 frameDropPerc 判卡顿，别盯 CPU）
    "unit": "percent",
    "before": { "value": 1.8, "n": 3, "route": "00000000--xxxx", "revision": "abc1234" },
    "after":  { "value": 0.2, "n": 3, "route": "00000000--yyyy", "revision": "def5678" },
    "delta": -1.6,
    "significance": "3 次重复，方向一致；未做显著性检验"   // 不许只写一次采样就下结论
  },
  "guard_tests": [                             // 锁住本结论的守卫（守卫被删 = 本验证作废）
    "openpilot/sunnypilot/carrot/tests/test_capnp_contract_guard.py"
  ],
  "boundaries": [                              // 边界声明（必填，至少 1 条）
    "PC 侧验证，不含设备端进程存活验证",
    "证据等级 <= 4，不构成可上车依据"
  ],
  "rollback": {                                // 回滚方案（改动类验证必填）
    "method": "git revert <sha>",
    "verified": false                          // 回滚是否真的演练过
  }
}
```

## 证据等级（1-8）

| 级 | 含义 |
|---|---|
| 1 | 纯推断/文档阅读，无命令 |
| 2 | 单次 grep/阅读，未对拍 |
| 3 | 可复算命令有输出（grep/AST/文本校验） |
| 4 | 单元测试通过（含 mock） |
| 5 | 设备端单元测试通过（skip=0 复核） |
| 6 | 离线回放（process_replay 喂 rlog.zst）通过 |
| 7 | 台架/offroad 实机运行验证 |
| 8 | onroad 实车验证 |

**规则**：
- 结论文字里的等级必须 ≤ 实际证据等级；写"已验证"最低要 4。
- **skip 必须 = 0** 才能宣称全绿；skip > 0 时 result 必须逐条写 skip_reason。
- offroad 证据（≤7）不得写成 onroad 结论；等级 8 前不得宣称"可上车"。
- 委派/子代理返回的"缺失/未移植/死代码/零引用/只写不读/断裂/重复"断言，必须独立复核后才可写入本文件。
