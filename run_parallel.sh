#!/bin/bash
# Run all ck*.txt cookies IN PARALLEL — mỗi cookie 1 process độc lập
# Mỗi process: 40 claims + transfer all → 51977054
# Sau khi tất cả xong → sleep → repeat
#
# MAX_RUNTIME_TOTAL env var (seconds):
#   0 (default) = infinite loop (for VPS)
#   >0 = stop after N seconds (for GitHub Actions / cron — e.g., 10800 = 3h)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
LOG=loop_parallel.log

# Config
MAX_PARALLEL="${MAX_PARALLEL:-0}"  # 0 = unlimited (mọi ck*.txt chạy cùng lúc)
MAX_RUNTIME_TOTAL="${MAX_RUNTIME_TOTAL:-0}"  # 0 = infinite; >0 = stop after N sec
MAX_RUNTIME_PER_SESSION="${MAX_RUNTIME_PER_SESSION:-600}"  # per-cookie timeout
SLEEP_BETWEEN_BATCHES="${SLEEP_BETWEEN_BATCHES:-15}"

START_EPOCH=$(date +%s)

echo "===== PARALLEL LOOP STARTED $(date) =====" >> $LOG
echo "[config] MAX_CLAIMS=${MAX_CLAIMS:-40} MAX_PARALLEL=$MAX_PARALLEL MAX_RUNTIME_TOTAL=$MAX_RUNTIME_TOTAL MAX_RUNTIME_PER_SESSION=$MAX_RUNTIME_PER_SESSION" >> $LOG

while true; do
    # Check total runtime limit
    if [ "$MAX_RUNTIME_TOTAL" -gt 0 ]; then
        NOW_EPOCH=$(date +%s)
        ELAPSED=$((NOW_EPOCH - START_EPOCH))
        if [ $ELAPSED -ge $MAX_RUNTIME_TOTAL ]; then
            echo "[loop] MAX_RUNTIME_TOTAL reached ($ELAPSED >= $MAX_RUNTIME_TOTAL sec). Exiting." >> $LOG
            break
        fi
        REMAINING=$((MAX_RUNTIME_TOTAL - ELAPSED))
        echo "[loop] Elapsed=${ELAPSED}s / ${MAX_RUNTIME_TOTAL}s, remaining=${REMAINING}s" >> $LOG
    fi

    echo "" >> $LOG
    echo "########## NEW PARALLEL BATCH: $(date) ##########" >> $LOG

    # List all ck*.txt files
    COOKIE_FILES=()
    for ck in ck*.txt; do
        [ -f "$ck" ] || continue
        COOKIE_FILES+=("$ck")
    done

    if [ ${#COOKIE_FILES[@]} -eq 0 ]; then
        echo "[loop] No ck*.txt files. Sleeping 60s..." >> $LOG
        sleep 60
        continue
    fi

    echo "[loop] Spawning ${#COOKIE_FILES[@]} parallel processes at $(date)" >> $LOG
    PIDS=()
    for ck in "${COOKIE_FILES[@]}"; do
        ck_log="${ck%.txt}.log"
        echo "  [spawn] $ck → log=$ck_log" >> $LOG
        MAX_CLAIMS="${MAX_CLAIMS:-40}" \
        HEADLESS=true \
        COOLDOWN=3 \
        REST_BETWEEN_RUNS=5 \
        MAX_RUNTIME="$MAX_RUNTIME_PER_SESSION" \
        SINGLE_COOKIE_FILE="$ck" \
        python3 "$SCRIPT_DIR/sam_reward_bot_v3_transfer.py" >> "$ck_log" 2>&1 &
        PIDS+=($!)
    done

    # Wait for all processes
    echo "[loop] Waiting for ${#PIDS[@]} processes..." >> $LOG
    FAILS=0
    for i in "${!PIDS[@]}"; do
        pid=${PIDS[$i]}
        ck=${COOKIE_FILES[$i]}
        wait $pid
        exit_code=$?
        if [ $exit_code -eq 0 ]; then
            echo "  [done] $ck (pid=$pid) exit=0 ✓" >> $LOG
        else
            echo "  [done] $ck (pid=$pid) exit=$exit_code ✗" >> $LOG
            FAILS=$((FAILS+1))
        fi
    done

    echo "[loop] Batch done at $(date). $FAILS/${#PIDS[@]} failed." >> $LOG

    # Per-cookie summary
    for ck in "${COOKIE_FILES[@]}"; do
        ck_log="${ck%.txt}.log"
        transferred=$(grep -c "✅ Transferred" "$ck_log" 2>/dev/null || echo 0)
        last_transfer=$(grep "✅ Transferred" "$ck_log" 2>/dev/null | tail -1)
        echo "  $ck: $transferred transfers total. Last: $last_transfer" >> $LOG
    done

    echo "[loop] Sleeping ${SLEEP_BETWEEN_BATCHES}s before next batch..." >> $LOG
    sleep "$SLEEP_BETWEEN_BATCHES"
done

echo "===== PARALLEL LOOP ENDED $(date) =====" >> $LOG
