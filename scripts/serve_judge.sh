#!/bin/bash
# Serve the promoted fine-tuned judge (Kev-0.8B + AGNews adapter, T fitted separately).
# Pinned: base jaredpalmer/kev-0.8b, adapter /home/kaizen/models/kev-agnews-08b (sha256 760d992911d13368).
# Usage: ./scripts/serve_judge.sh [--port 8020]
# Waits until /v1/models answers, then exits 0 (server keeps running detached).
set -u
PORT="${2:-8020}"
RUN_DIR="${KEV_RUN_DIR:-/home/kaizen/models/kev-agnews-08b}"
cd /home/kaizen/repos/kev-local || exit 1
setsid nohup env KEV_CUDA_GRAPHS=0 /home/kaizen/.local/bin/uv run --extra serve \
  python -m kev.serve --run "$RUN_DIR" --port "$PORT" \
  > /tmp/opencode/kev-ft-serve.log 2>&1 < /dev/null &
for i in $(seq 1 40); do
  sleep 5
  if curl -s -m 3 "http://127.0.0.1:${PORT}/v1/models" | grep -q kev-latest; then
    echo "judge ready on :$PORT ($RUN_DIR)"
    exit 0
  fi
done
echo "judge did NOT become ready; see /tmp/opencode/kev-ft-serve.log"
exit 1
