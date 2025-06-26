#!/usr/bin/env bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"

export FINGERPRINT="TOYOTA_WILDLANDER"
export SKIP_FW_QUERY="1"
$DIR/../launch_openpilot.sh
