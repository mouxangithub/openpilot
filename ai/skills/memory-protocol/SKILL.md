# 记忆协议

## 何时记录

- 用户明确偏好（跟车风格、ALKA 习惯）
- 车型年款、改装、已知问题
- 一次成功的调优组合

## 如何记录

`update_agent_memory`：`note` + 可选 `vehicle_profile` 字段。

## 禁止

- API Key、密码
- 未经确认的写入计划（先 `diff_params`）

对话开始已注入设备记忆，勿重复啰嗦。
