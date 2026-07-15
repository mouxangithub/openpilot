# 驾驶模型选择

1. `read_params` → `dp_dev_model_list`（JSON）、`dp_dev_model_selected`
2. `list_dp_settings` 中模型相关项
3. 静止 + 用户确认 → `select_driving_model`
4. 必要时 `restart_ui`

空字符串模型 = AUTO。切换后建议短程测试再长途。
