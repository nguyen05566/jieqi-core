# JieqiCore

JieqiCore là engine C++/UCI dành riêng cho bot cờ úp (Jieqi) chạy trên Linux.
Dự án được tách từ engine PikaJieQi mà Mistboard sử dụng; không chứa frontend,
WebSocket bot, capture logs, database, web app hay WebAssembly.

## Mục tiêu

- một binary Linux nhỏ gọn để bot gọi qua stdin/stdout;
- giữ protocol `position startpos moves ...` đang dùng trong bot `nguyen05566/zai`;
- sửa các lỗi correctness/undefined behavior đã tìm thấy trong engine Mistboard;
- mặc định gộp chance outcomes trong không gian xác suất thắng (sigmoid);
- có thể build lại legacy chance aggregation để A/B công bằng;
- không cần file NNUE: bản hiện tại dùng classical evaluation.

## Các thay đổi chính trong 0.1.0

- sửa out-of-bounds `psqDark[5]`;
- khởi tạo `checkSquares[ADVISOR_B]`;
- truyền `capturedPiece` vào resolved dark state;
- khi dark-depth cap chặn enumeration, dùng static evaluation thay vì bỏ nước hợp lệ;
- sửa biểu thức repetition draw bị no-op;
- sigmoid chance aggregation theo multiplicity, vẫn giữ forced-loss guard của Mistboard;
- bỏ phần ứng dụng Mistboard và browser/WASM; chỉ giữ native UCI engine và tests.

Không có tuyên bố tăng Elo ở phiên bản này. Sigmoid là candidate cần paired self-play.
Kết quả build/test cục bộ nằm trong [`RELEASE_NOTES.md`](RELEASE_NOTES.md).

## Build trên Linux

Yêu cầu: GCC/G++, GNU Make và CPU x86-64 có SSE4.1 + POPCNT (GitHub `ubuntu-latest` đáp ứng).

```bash
./scripts/build-linux.sh
# binary: bin/jieqi-core
```

Hoặc build trực tiếp:

```bash
make build
# binary: src/jieqi-core
```

Build baseline dùng chance aggregation cũ:

```bash
make legacy
# binary: src/jieqi-core
```

## Test

```bash
make test          # unit + UCI smoke + deterministic search
make sanitize      # ASan + UBSan regression
```

Valgrind nếu máy đã cài:

```bash
make valgrind
```

## Dùng với bot `nguyen05566/zai`

Bot chỉ cần đường dẫn binary:

```bash
export MISTBOARD_JIEQI_ENGINE=/absolute/path/to/jieqi-core/bin/jieqi-core
python3 -u cup_bot_mistboard.py
```

Workflow GitHub có thể build như sau:

```yaml
- name: Build JieqiCore
  run: |
    git clone <JIEQI_CORE_REPOSITORY_URL> jieqi-core
    jieqi-core/scripts/build-linux.sh "$GITHUB_WORKSPACE/jieqi-core-bin"

- name: Run bot
  env:
    MISTBOARD_JIEQI_ENGINE: ${{ github.workspace }}/jieqi-core-bin
  run: python3 -u cup_bot_mistboard.py
```

Nên pin bằng commit SHA hoặc release tag; không build trực tiếp từ branch tip.

## Protocol cần cho bot

JieqiCore hỗ trợ UCI và move suffix của PikaJieQi:

- `a3a4`: nước không kèm role reveal;
- `a3a4R`: quân di chuyển được lật thành xe đỏ; nếu source đã mở thì ký tự thứ 5 là quân bị bắt;
- move 6 ký tự: chứa cả role quân di chuyển và quân bị bắt.

Ví dụ:

```text
uci
setoption name Threads value 1
setoption name Hash value 128
isready
ucinewgame
position startpos moves a3a4R
go nodes 100000
```

Engine cũng nhận custom Jieqi FEN năm field:

```text
xxxxkxxxx/9/1x5x1/x1x1x1x1x/9/9/X1X1X1X1X/1X5X1/9/XXXXKXXXX w R2A2C2P5N2B2r2a2c2p5n2b2 0 1
```

`setflip` không phải command của engine. Việc đổi góc nhìn tọa độ phải do adapter bot xử lý trước khi gửi move/FEN.

## A/B sigmoid đúng cách

So sánh default build với `make legacy` bằng:

- cùng compiler/flags/CPU;
- `Threads=1`, cùng Hash;
- fixed node budget, movetime chỉ là watchdog;
- cùng hidden-deal seed, đổi màu theo cặp;
- theo dõi W/D/L, timeout, crash, illegal/rejected move và parser failure.

## License

GPL-3.0-or-later. Xem `Copying.txt`, `AUTHORS` và `PROVENANCE.md`.
