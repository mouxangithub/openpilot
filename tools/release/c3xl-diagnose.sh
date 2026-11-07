#!/usr/bin/env bash
# C3XL 内置熊只读诊断脚本（不写任何参数、不刷任何东西）
# 用法（设备上执行）：
#   bash <(curl -fsSL https://cnb.cool/mouxancnb/openpilot/-/git/raw/test/tools/release/c3xl-diagnose.sh)
# 提示：输出较长时建议先落盘再看： bash <(curl ...) 2>&1 | tee /data/diag.log && cat /data/diag.log
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
EOF

echo "===== [5] pandad 循环现场（journal 带时间戳，判断为什么掉线） ====="
journalctl -u comma.service --no-pager -n 800 2>/dev/null | grep -i -E 'pandad|DFU|recover|flash|assert|fatal|ValueError|heartbeat|uncaught|BUSY' | tail -70 || echo "journalctl 无 comma.service 日志"

echo "===== [6] 熊详情（逐项容错；提示 BUSY = 守护进程正占着接口，属正常） ====="
"$PY" - <<'EOF' 2>&1 | tail -20
import os
from panda import Panda, FW_PATH

def show(name, fn):
    try:
        print(name, fn())
    except Exception as e:
        print(name, '出错:', type(e).__name__, str(e)[:100])

try:
    serials = Panda.list()
    if not serials:
        raise RuntimeError('无 panda 可连（看 [3] 节判断设备处于什么状态）')
    p = Panda(serials[0])
except Exception as e:
    if 'BUSY' in str(e):
        print('接口被 pandad 占用（守护进程正在连熊，是好事）；等它掉线瞬间重跑本脚本')
    print('无法连接:', type(e).__name__, str(e)[:120])
    raise SystemExit(0)

print('serial:', serials[0])
show('bootstub:', lambda: p.bootstub)
show('hw_type:', lambda: repr(p.get_type()))   # 新库返回单字节 bytearray，用 repr
show('mcu:', lambda: p.get_mcu_type())
show('version:', lambda: p.get_version())
show('is_internal:', lambda: p.is_internal())
show('health:', lambda: str(p.health())[:220])
show('sig_match:', lambda: Panda.get_signature_from_firmware(os.path.join(FW_PATH, p.get_mcu_type().config.app_fn)) == p.get_signature())
EOF

echo "===== 诊断完成，请把以上全部输出回传（重点 [5] 循环现场） ====="
