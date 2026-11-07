#!/usr/bin/env bash
# C3XL 内置熊只读诊断脚本（不写任何参数、不刷任何东西）
# 用法（设备上执行）：
#   bash <(curl -fsSL https://cnb.cool/mouxancnb/openpilot/-/git/raw/test/tools/release/c3xl-diagnose.sh)
set -u

echo "===== [1] 系统与平台 ====="
uname -a | cut -c1-90
cat /PARAMS 2>/dev/null | head -1
ls /dev/spidev* 2>/dev/null || echo "spidev: 不存在（SPI 熊在此系统不可用）"
ls /sys/class/gpio 2>/dev/null | grep -c . || true

echo "===== [2] 安装的分支与版本 ====="
cat /data/openpilot/git_src_commit 2>/dev/null || echo "无 git_src_commit（可能非打包树）"
ls /data/openpilot/panda/board/obj/*.signed 2>/dev/null | head -4
cat /data/openpilot/panda/board/obj/version 2>/dev/null; echo

echo "===== [3] USB 设备（熊的三种状态） ====="
echo "应用模式应为 3801:ddcc | DFU 模式为 0483:df11 | 都没有 = 总线静默"
lsusb | grep -E '3801|0483' || echo "USB 上没有任何 panda / DFU 设备"

PY=/usr/local/venv/bin/python3.12
[ -x "$PY" ] || PY=python3
export PYTHONPATH=/data/openpilot:/data/openpilot/openpilot:/usr/local/venv/lib/python3.12/site-packages

echo "===== [4] panda 库视角 ====="
"$PY" - <<'EOF' 2>&1 | tail -12
from panda import Panda, PandaDFU
try:
    print('Panda.list():', Panda.list())
except Exception as e:
    print('Panda.list() 异常:', type(e).__name__, str(e)[:100])
try:
    print('PandaDFU.list():', PandaDFU.list())
except Exception as e:
    print('PandaDFU.list() 异常:', type(e).__name__, str(e)[:100])
try:
    print('Panda.spi_list():', Panda.spi_list())
except Exception as e:
    print('spi_list 异常:', type(e).__name__, str(e)[:100])
EOF

echo "===== [5] pandad 日志（最近一次刷写尝试） ====="
LOG=$(ls -t /data/media/0/olog/*.log 2>/dev/null | head -1)
[ -z "$LOG" ] && LOG=$(journalctl -u comma.service --no-pager -n 400 2>/dev/null | grep -i -E 'pandad|panda' | tail -40 || true)
if [ -n "$LOG" ] && [ -f "$LOG" ]; then
  grep -i -E 'pandad|flash|recover|DFU|panda' "$LOG" 2>/dev/null | tail -30
else
  journalctl -u comma.service --no-pager -n 300 2>/dev/null | grep -i -E 'pandad\.|panda|flash|recover' | tail -30
fi

echo "===== [6] 熊详情（如应用模式可达） ====="
"$PY" - <<'EOF' 2>&1 | tail -12
import os
from panda import Panda, FW_PATH
try:
    serials = Panda.list()
    if not serials:
        raise RuntimeError('无 panda 可连')
    p = Panda(serials[0])
    print('serial:', serials[0])
    print('bootstub:', p.bootstub)
    print('hw_type:', hex(p.get_type()))
    print('mcu:', p.get_mcu_type())
    print('version:', p.get_version())
    print('is_internal:', p.is_internal())
    fn = os.path.join(FW_PATH, p.get_mcu_type().config.app_fn)
    print('sig_match:', Panda.get_signature_from_firmware(fn) == p.get_signature())
    p.close()
except Exception as e:
    print('无法连接:', type(e).__name__, str(e)[:120])
EOF

echo "===== 诊断完成，请把以上全部输出回传 ====="
