# 网络与联机诊断

无法 engage、devsync 失败、无法拉路线时，按此顺序排查：

1. `network_diagnostics()` — WiFi、外网 ping、comma 登录
2. 若需同步代码到车机：先 `pc_devsync_status(device_ip=...)`，再 `pc_devsync_run(device_ip=..., confirm=true)`
3. PC 开发：`git_status` / `git_pull(confirm=true)` 后再 devsync
4. 车机仍离线：`manager_control(action=status)`、`read_manager_log`
5. **Konik 配对**（本 fork 替代 comma connect）：`konik_connect_status` → 见 skill **Konik 替代 Connect**

常见问题：
- SSH 未配置 → 终端执行 `ssh comma@<IP>` 完成主机密钥
- 无 WiFi → `run_shell_command("iwconfig")` 或 `network_diagnostics`
- Comma 未登录 → `comma_auth_status`，PC 上 `pc_auth_login_hint`
