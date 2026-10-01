#!/bin/bash
# Monday reminder: longitudinal row should exist — review it with opencode.
# Runs via systemd user timer (longitudinal-notify.timer, Mondays 09:00),
# after the 06:00 probe. Only notifies; never fails loudly.
REPO=/home/kaizen/repos/cognitive-swarm-service
TODAY=$(date +%F)
ROW=$(grep -h "\"date\": \"$TODAY\"" "$REPO/data/longitudinal_log.jsonl" 2>/dev/null | tail -1)
if [ -n "$ROW" ]; then
  ACC=$(echo "$ROW" | grep -o '"acc": [0-9.]*')
  notify-send -a "swarm" -u normal "Swarm: fila longitudinal lista" \
    "$TODAY $ACC — revísala con opencode (docs/LONGITUDINAL.md)" 2>/dev/null
else
  notify-send -a "swarm" -u critical "Swarm: sin fila longitudinal hoy" \
    "El probe de las 06:00 no escribió. Revisa data/longitudinal_cron.log" 2>/dev/null
fi
