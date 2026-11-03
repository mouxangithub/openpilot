# Compatibility shim.
# Carrot/legacy ported code (cluster, carrot_serv, process_crash, bluetooth
# protocol, debug tools) imports the hardware abstraction from
# ``openpilot.system.hardware``. In this repo the real implementation lives in
# ``openpilot.common.hardware`` — re-export it here so both import paths work.
import os

from openpilot.common.hardware import AGNOS, COMMA_HARDWARE, PC, HARDWARE  # noqa: F401

# Legacy carrot flag: only true on tici/tizi boards, never on AGNOS devices.
TICI = os.path.isfile('/TICI')  # noqa: F401
