# 调参后验证

1. `save_tune_snapshot` 改参前
2. 短路线试驾
3. `compare_tune_ab` / `score_tune_session` 对比
4. 变差则 `restore_tune_snapshot` 或 `sp_rollback_last_tune`
5. `list_audit_trail` 查写入记录
