#!/bin/bash
# Serve local Laya judge (ONNX CPU, ~33ms/decision). Honors LAYA_PORT (default 8021
# here so the demo API keeps :8000 — laya-serve ignores --port flags).
# First run downloads the ~421M checkpoint. Waits until ready.
set -u
PORT="${1:-8021}"
setsid nohup env LAYA_PORT="$PORT" LAYA_PRELOAD=1 laya-serve \
  > /tmp/opencode/laya-serve.log 2>&1 < /dev/null &
for i in $(seq 1 40); do
  sleep 5
  if curl -s -m 3 "http://127.0.0.1:${PORT}/v1/systemone" -H 'content-type: application/json' \
      -d '{"state":"hi","questions":{"a":{"type":"noul","instructions":"Is this a greeting?"}}}' \
      | grep -q answers; then
    echo "laya ready on :$PORT"
    exit 0
  fi
done
echo "laya did NOT become ready; see /tmp/opencode/laya-serve.log"
exit 1
