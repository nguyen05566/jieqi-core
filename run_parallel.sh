#!/bin/bash
# Run all ck*.txt cookies IN PARALLEL — mỗi cookie 1 process độc lập
# Mỗi process: 40 claims + transfer all → 51977054
# Sau khi tất cả xong → sleep → repeat

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
LOG=loop_parallel.log

# Optional: limit số process chạy song song (default = all ck*.txt files)
MAX_PARALLEL="${MAX_PARALLEL:-0}"  # 0 = unlimited (mọi ck*.txt chạy cùng lúc)

echo "===== PARALLEL LOOP STARTED $(date) =====" >> $LOG
echo "[config] MAX_CLAIMS=${MAX_CLAIMS:-40} MAX_PARALLEL=$MAX_PARALLEL" >> $LOG

while true; do
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
        MAX_RUNTIME=600 \
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

    # Brief summary: count transfers in each cookie's log
    for ck in "${COOKIE_FILES[@]}"; do
        ck_log="${ck%.txt}.log"
        # Count successful transfers in this cookie's log
        transferred=$(grep -c "✅ Transferred" "$ck_log" 2>/dev/null || echo 0)
        last_transfer=$(grep "✅ Transferred" "$ck_log" 2>/dev/null | tail -1)
        echo "  $ck: $transferred transfers total. Last: $last_transfer" >> $LOG
    done

    echo "[loop] Sleeping 15s before next batch..." >> $LOG
    sleep 15
done
