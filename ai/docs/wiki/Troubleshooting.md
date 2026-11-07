# Troubleshooting

## 无法打开 Web

- 确认 `python3 -m ai.aid` 在运行  
- 防火墙放行 **5090**  
- `op status` 检查 configured  

## AI 不回复

- 设置 → 模型 API Key 是否有效  
- 「测试连接」  
- 查看用量是否超限  

## 无法 Engage

用向导，不要自己猜参数：

- Web：**开不起来排查**  
- CLI：`op doctor`  
- 聊天：`/开不起来`  

## 改参后变差

- Web：说「撤销上次调参」  
- 设置 → 调参护照 / 快照恢复  

## Web 终端没有 op 命令

```bash
ls -l $OPENPILOT_ROOT/op
# 重新运行 install.sh 或：
export PATH="$OPENPILOT_ROOT/ai/scripts:$OPENPILOT_ROOT:$PATH"
```

## 仍无法解决

[提交 Bug Issue](https://github.com/mouxangithub/ai/issues/new?template=op_bug.yml)（附 `op status` 与版本号）

更多：仓库 [TROUBLESHOOTING.md](https://github.com/mouxangithub/ai/blob/main/docs/TROUBLESHOOTING.md)
