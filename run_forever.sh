#!/bin/bash
# Infinite loop: claim 40 + transfer all → 51977054
# Auto-picks up ck*.txt files (ck1.txt, ck2.txt, ...) via sam_reward_bot_v3.py's load_all_cookie_sets
# Logs to loop.log

# Portable: cd to script's own directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
LOG=loop.log

echo "===== STARTED $(date) =====" >> $LOG

while true; do
    echo "" >> $LOG
    echo "########## NEW RUN: $(date) ##########" >> $LOG
    MAX_CLAIMS=40 \
    HEADLESS=true \
    COOLDOWN=3 \
    REST_BETWEEN_RUNS=5 \
    MAX_RUNTIME=600 \
    python3 "$SCRIPT_DIR/sam_reward_bot_v3_transfer.py" >> $LOG 2>&1
    EXIT_CODE=$?
    echo "[loop] Run exited with code $EXIT_CODE at $(date). Sleeping 10s..." >> $LOG
    sleep 10
done
