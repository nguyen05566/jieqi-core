#!/bin/bash
# Test script chạy ck1.py trong 10 phút

echo "=========================================="
echo "Test ck1.py - 10 phút"
echo "=========================================="
echo ""

# Thời gian bắt đầu
START_TIME=$(date +%s)
END_TIME=$((START_TIME + 600))  # 10 phút = 600 giây

echo "Bắt đầu lúc: $(date '+%H:%M:%S')"
echo "Kết thúc lúc: $(date -d @$END_TIME '+%H:%M:%S')"
echo ""

# Cấu hình môi trường
MAX_CLAIMS=1  # Chỉ claim 1 lần rồi transfer
TRANSFER_DEST_ID=68307415
HEADLESS=true
COOLDOWN=3
REST_BETWEEN_RUNS=5
MAX_RUNTIME=600

export MAX_CLAIMS TRANSFER_DEST_ID HEADLESS COOLDOWN REST_BETWEEN_RUNS MAX_RUNTIME

echo "Cấu hình:"
echo "  MAX_CLAIMS=$MAX_CLAIMS"
echo "  TRANSFER_DEST_ID=$TRANSFER_DEST_ID"
echo "  HEADLESS=$HEADLESS"
echo "  COOLDOWN=$COOLDOWN"
echo "  REST_BETWEEN_RUNS=$REST_BETWEEN_RUNS"
echo "  MAX_RUNTIME=$MAX_RUNTIME"
echo ""

# Chạy bot
python3 ck1.py

EXIT_CODE=$?
DUR=$(( $(date +%s) - START_TIME ))

echo ""
echo "=========================================="
echo "Kết thúc test"
echo "Thời gian chạy: ${DUR} giây"
echo "Mã thoát: $EXIT_CODE"
echo "=========================================="
