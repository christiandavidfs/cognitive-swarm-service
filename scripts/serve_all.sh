#!/bin/bash
# Full stack: fine-tuned judge (:8020) + API (:8000). Survives nothing (nohup),
# but restarts deterministically from pins. For persistence across reboots,
# wire these two commands into systemd/cron — see docs/MEASUREMENTS.md open gates.
# Usage: ./scripts/serve_all.sh
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
"$REPO/scripts/serve_judge.sh" --port 8020 || exit 1
setsid nohup env \
  PYTHONPATH=/home/kaizen/repos/cognitive-swarm \
  BACKENDS=cognitive_swarm \
  MEMORY_PATH="$REPO/data/verified_memory.json" \
  JUDGE=jev JEV_VIA=typesafe \
  TYPESAFE_BASE_URL=http://127.0.0.1:8020 TYPESAFE_API_KEY=local \
  JUDGE_TEMPERATURE=1.9 \
  /home/linuxbrew/.linuxbrew/bin/python3 -m uvicorn service.app:app \
  --host 127.0.0.1 --port 8000 > /tmp/opencode/demo-server.log 2>&1 < /dev/null &
for i in $(seq 1 24); do
  sleep 5
  if curl -s -m 3 http://127.0.0.1:8000/health | grep -q '"status":"ok"'; then
    echo "api ready on :8000 (judge: FT :8020, T=1.9)"
    exit 0
  fi
done
echo "api did NOT become ready; see /tmp/opencode/demo-server.log"
exit 1
