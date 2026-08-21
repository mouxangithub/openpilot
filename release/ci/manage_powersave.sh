#!/usr/bin/env bash
# CI-friendly powersave toggle for comma three (no Python / capnp required).
set -euo pipefail

write_sysfs() {
  echo "$1" | sudo tee "$2" > /dev/null
}

if [[ "${1:-}" == "--enable" ]]; then
  powersave=true
elif [[ "${1:-}" == "--disable" ]]; then
  powersave=false
else
  echo "Usage: $0 --enable|--disable" >&2
  exit 1
fi

for i in 4 5 6 7; do
  path="/sys/devices/system/cpu/cpu${i}/online"
  if [[ -f "$path" ]]; then
    if $powersave; then write_sysfs 0 "$path"; else write_sysfs 1 "$path"; fi
  fi
done

for n in 0 4; do
  gov="/sys/devices/system/cpu/cpufreq/policy${n}/scaling_governor"
  if [[ ! -f "$gov" ]]; then
    continue
  fi
  if $powersave && [[ "$n" == "4" ]]; then
    continue
  fi
  if $powersave; then
    write_sysfs ondemand "$gov"
  else
    write_sysfs performance "$gov"
    max_freq="/sys/devices/system/cpu/cpufreq/policy${n}/scaling_max_freq"
    if [[ -f "$max_freq" ]]; then
      write_sysfs 1689600 "$max_freq"
    fi
  fi
done

state=enabled
$powersave || state=disabled
echo "Power save mode set to: [$state]"
echo "Number of CPU cores available now: [$(nproc)]"
