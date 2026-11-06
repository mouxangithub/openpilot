#!/usr/bin/env bash

# openpilot launcher with uninstall fallback.
# comma.sh does `exec /data/continue.sh` whenever the file exists; if openpilot
# has been uninstalled (or the tree is broken), a bare exec exits the shell and
# systemd restarts comma.sh into the same failing exec forever — the device
# appears stuck on the comma logo. On a missing/broken tree we remove our
# launcher and exit so comma.sh falls back to the standard setup/installer flow.

while true; do
  if [ -f /data/openpilot/launch_openpilot.sh ]; then
    cd /data/openpilot
    exec ./launch_openpilot.sh
  fi
  # openpilot uninstalled or broken: hand control back to comma.sh
  rm -f /data/continue.sh
  exit 1
done
