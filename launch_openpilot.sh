#!/usr/bin/env bash
if [[ "$(cat /data/params/d/EnableConnect)" == "2" ]]; then
  export API_HOST="https://api.carrotpilot.app"
  export ATHENA_HOST="wss://athena.carrotpilot.app"
fi
  export API_HOST=https://api.konik.ai
  export ATHENA_HOST=wss://athena.konik.ai
exec ./launch_chffrplus.sh
