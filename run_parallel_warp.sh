#!/bin/bash
# run_parallel_warp.sh — Parallel bot + Cloudflare WARP auto IP rotation
#
# Flow:
#   1. Check WARP installed (auto-install if missing)
#   2. Connect WARP (route bot traffic via Cloudflare)
#   3. Spawn N parallel processes (one per ck*.txt) — all use WARP IP
#   4. Wait for all
#   5. (Optional) Rotate WARP session to get new IP for next batch
#   6. Repeat
#
# Cloudflare WARP: free, unlimited, no registration needed
# Install: https://pkg.cloudflareclient.com/
#
# Note: WARP gives 1 shared IP per region. For TRUE multi-IP per cookie,
# use residential proxies (BrightData, Smartproxy). But WARP is good enough
# for small scale (3-5 cookies) and avoids direct exposure of your VPS IP.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
LOG=loop_parallel_warp.log

# === Config ===
MAX_CLAIMS="${MAX_CLAIMS:-40}"
MAX_RUNTIME_PER_SESSION="${MAX_RUNTIME_PER_SESSION:-600}"
SLEEP_BETWEEN_BATCHES="${SLEEP_BETWEEN_BATCHES:-15}"
WARP_ROTATE_BETWEEN_BATCHES="${WARP_ROTATE_BETWEEN_BATCHES:-true}"  # disconnect+reconnect for new IP
WARP_AUTO_INSTALL="${WARP_AUTO_INSTALL:-false}"  # set to true to auto-install

# === WARP helpers ===
warp_check_installed() {
    command -v warp-cli >/dev/null 2>&1
}

warp_install() {
    echo "[warp] Installing Cloudflare WARP..." | tee -a "$LOG"
    if command -v apt >/dev/null 2>&1; then
        # Ubuntu/Debian
        curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg 2>/dev/null
        echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list >/dev/null
        sudo apt update -qq && sudo apt install -y cloudflare-warp 2>&1 | tail -3
    elif command -v yum >/dev/null 2>&1; then
        # RHEL/CentOS/Fedora
        sudo rpm --import https://pkg.cloudflareclient.com/pubkey.gpg
        sudo dnf install -y "https://pkg.cloudflareclient.com/cloudflare-warp-1.0.0-1.x86_64.rpm" 2>&1 | tail -3 || \
        sudo yum install -y "https://pkg.cloudflareclient.com/cloudflare-warp-1.0.0-1.x86_64.rpm" 2>&1 | tail -3
    else
        echo "[warp] ❌ Cannot auto-install (need apt or yum). Manual install: https://pkg.cloudflareclient.com/" | tee -a "$LOG"
        return 1
    fi
    # Register (1 time, no email needed)
    warp-cli registration new 2>&1 | tee -a "$LOG"
    echo "[warp] ✓ Installed + registered" | tee -a "$LOG"
}

warp_get_ip() {
    curl -s --max-time 5 https://ifconfig.me 2>/dev/null || echo "unknown"
}

warp_connect() {
    echo "[warp] Connecting..." | tee -a "$LOG"
    warp-cli connect 2>&1 | tee -a "$LOG"
    # Wait for connection
    for i in $(seq 1 10); do
        if warp-cli status 2>&1 | grep -q "Connected"; then
            local new_ip=$(warp_get_ip)
            echo "[warp] ✓ Connected. IP: $new_ip" | tee -a "$LOG"
            return 0
        fi
        sleep 1
    done
    echo "[warp] ⚠ Connection timeout (status: $(warp-cli status 2>&1 | head -1))" | tee -a "$LOG"
    return 1
}

warp_disconnect() {
    warp-cli disconnect 2>&1 >/dev/null
    echo "[warp] Disconnected" | tee -a "$LOG"
}

warp_rotate() {
    # Disconnect + reconnect to potentially get new IP from WARP pool
    echo "[warp] Rotating IP (disconnect + reconnect)..." | tee -a "$LOG"
    warp_disconnect
    sleep 2
    warp_connect
}

# === Main loop ===
echo "===== PARALLEL+WARP LOOP STARTED $(date) =====" >> "$LOG"
echo "[config] MAX_CLAIMS=$MAX_CLAIMS ROTATE=$WARP_ROTATE_BETWEEN_BATCHES" >> "$LOG"

# Initial setup
if ! warp_check_installed; then
    if [ "$WARP_AUTO_INSTALL" = "true" ]; then
        warp_install || { echo "[fatal] WARP install failed, aborting" | tee -a "$LOG"; exit 1; }
    else
        echo "[fatal] WARP not installed. Set WARP_AUTO_INSTALL=true or run install manually:" | tee -a "$LOG"
        echo "  See: https://pkg.cloudflareclient.com/" | tee -a "$LOG"
        echo "  Or just run without WARP: ./run_parallel.sh" | tee -a "$LOG"
        exit 1
    fi
fi

# Initial connection
ORIG_IP=$(warp_get_ip)
echo "[warp] Original VPS IP: $ORIG_IP" | tee -a "$LOG"
warp_connect
WARP_IP=$(warp_get_ip)
echo "[warp] WARP IP: $WARP_IP (different from $ORIG_IP: $([ "$ORIG_IP" != "$WARP_IP" ] && echo yes || echo no))" | tee -a "$LOG"

# Trap exit to disconnect WARP + cleanup
cleanup() {
    echo "[cleanup] Disconnecting WARP..." | tee -a "$LOG"
    warp_disconnect
    pkill -f sam_reward_bot_v3_transfer 2>/dev/null
    exit 0
}
trap cleanup INT TERM EXIT

# Main loop
while true; do
    echo "" | tee -a "$LOG"
    echo "########## NEW PARALLEL+WARP BATCH: $(date) ##########" | tee -a "$LOG"

    # Optionally rotate WARP IP before each batch
    if [ "$WARP_ROTATE_BETWEEN_BATCHES" = "true" ]; then
        warp_rotate
        CURRENT_IP=$(warp_get_ip)
        echo "[warp] Current IP for this batch: $CURRENT_IP" | tee -a "$LOG"
    fi

    # List cookies
    COOKIE_FILES=()
    for ck in ck*.txt; do
        [ -f "$ck" ] || continue
        COOKIE_FILES+=("$ck")
    done
    if [ ${#COOKIE_FILES[@]} -eq 0 ]; then
        echo "[loop] No ck*.txt files. Sleeping 60s..." | tee -a "$LOG"
        sleep 60
        continue
    fi

    echo "[loop] Spawning ${#COOKIE_FILES[@]} parallel processes at $(date) (WARP IP: $CURRENT_IP)" | tee -a "$LOG"
    PIDS=()
    for ck in "${COOKIE_FILES[@]}"; do
        ck_log="${ck%.txt}.log"
        echo "  [spawn] $ck → log=$ck_log" | tee -a "$LOG"
        MAX_CLAIMS="$MAX_CLAIMS" \
        HEADLESS=true \
        COOLDOWN=3 \
        REST_BETWEEN_RUNS=5 \
        MAX_RUNTIME="$MAX_RUNTIME_PER_SESSION" \
        SINGLE_COOKIE_FILE="$ck" \
        python3 "$SCRIPT_DIR/sam_reward_bot_v3_transfer.py" >> "$ck_log" 2>&1 &
        PIDS+=($!)
    done

    # Wait for all
    echo "[loop] Waiting for ${#PIDS[@]} processes..." | tee -a "$LOG"
    FAILS=0
    for i in "${!PIDS[@]}"; do
        pid=${PIDS[$i]}
        ck=${COOKIE_FILES[$i]}
        wait $pid
        exit_code=$?
        if [ $exit_code -eq 0 ]; then
            echo "  [done] $ck (pid=$pid) exit=0 ✓" | tee -a "$LOG"
        else
            echo "  [done] $ck (pid=$pid) exit=$exit_code ✗" | tee -a "$LOG"
            FAILS=$((FAILS+1))
        fi
    done

    # Summary per cookie
    echo "" | tee -a "$LOG"
    echo "[loop] Batch summary at $(date) ($FAILS/${#PIDS[@]} failed, WARP IP: $CURRENT_IP):" | tee -a "$LOG"
    for ck in "${COOKIE_FILES[@]}"; do
        ck_log="${ck%.txt}.log"
        # Get last transfer + count
        last_transfer=$(grep "✅ Transferred" "$ck_log" 2>/dev/null | tail -1)
        total_transfers=$(grep -c "✅ Transferred" "$ck_log" 2>/dev/null || echo 0)
        echo "  $ck: $total_transfers transfers total. Last: ${last_transfer:0:80}" | tee -a "$LOG"
    done

    echo "[loop] Batch done at $(date). Sleeping ${SLEEP_BETWEEN_BATCHES}s before next..." | tee -a "$LOG"
    sleep "$SLEEP_BETWEEN_BATCHES"
done
