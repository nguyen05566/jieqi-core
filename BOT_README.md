# Sâm Lốc Bot v3 + Transfer Xu — Infinite Loop

Production-ready bot tự động claim video rewards + transfer xu về hub account.

## Files

| File | Purpose |
|---|---|
| `sam_reward_bot_v3_transfer.py` | Bot chính: Playwright + claim video reward × N + transfer xu |
| `run_forever.sh` | Bash wrapper: infinite loop, tự restart sau mỗi session |
| `ck1.txt`, `ck2.txt`, `ck3.txt` | Cookies Facebook (mỗi file = 1 FB account) |
| `sam_reward_bot_v3.py` | (Đã có sẵn) v3 gốc, không có transfer logic |

## Cách chạy

### 1. Cài đặt dependencies (chỉ lần đầu)

```bash
pip install playwright websocket-client
playwright install chromium
```

### 2. Chuẩn bị cookies

Mỗi file `ckN.txt` chứa 1 dòng cookies Facebook (copy từ DevTools → Application → Cookies → facebook.com):

```
datr=...; sb=...; c_user=...; xs=...; ...
```

Bot tự cycle qua `ck1.txt → ck2.txt → ck3.txt → ck1.txt → ...`

### 3. Test 1 session trước

```bash
MAX_CLAIMS=40 HEADLESS=true python3 sam_reward_bot_v3_transfer.py
```

### 4. Loop forever (background)

```bash
nohup ./run_forever.sh > /dev/null 2>&1 &
echo $! > loop.pid
disown

# Monitor:
tail -f loop.log

# Stop:
kill $(cat loop.pid)
pkill -f sam_reward_bot_v3_transfer
```

## Cấu hình (env vars)

| Var | Default | Ý nghĩa |
|---|---|---|
| `MAX_CLAIMS` | 40 | Số video reward claims / session |
| `HEADLESS` | true | false = mở browser visible (debug) |
| `COOLDOWN` | 3 | Sleep giây giữa các claim |
| `REST_BETWEEN_RUNS` | 5 | Sleep giây giữa các session |
| `MAX_RUNTIME` | 600 | Timeout 1 session (giây) |
| `TRANSFER_DEST_ID` | 51977054 | Hub account ID nhận xu |
| `TRANSFER_ENABLED` | true | Bật/tắt transfer logic |

## Logic đã verify (đã test thành công)

Per session:
1. Open Playwright + login FB với cookies
2. Navigate to `https://www.facebook.com/gaming/play/sam_loc_vh`
3. Wait game frame + WS connected
4. Loop MAX_CLAIMS times:
   - `createTable()` → select highest bet → click CREATE
   - Click "watch video" button (triggers ad)
   - `connection.send(OutboundMessage("VIDEO_REWARD") + writeByte(1))` → claim reward
   - Update balance via `Ads.RewardedVideo.videoIndex++`
5. After loop:
   - Read balance from `.chipBalance` DOM
   - `connection.send(OutboundMessage("TRANSFER") + writeLong(DEST_ID) + writeLong(balance))` → transfer all
6. Close browser, sleep, restart

Test result (ck1.txt alone):
- Session 1: 7 claims OK (+8,300 xu), transferred 82,620 xu
- Session 2: 34 claims OK (+39,500 xu), transferred 39,500 xu
- **Total: 41 claims, 47,800 xu reward, 122,120 xu → 51977054**

## Thêm cookies mới

```bash
echo "datr=...; c_user=...; xs=...; ..." > ck4.txt
echo "datr=...; c_user=...; xs=...; ..." > ck5.txt
# Bot tự pick ở session kế tiếp
```

## Quan trọng

- **Cookies FB expire** sau 2-3 giờ — refresh khi bot báo "Not logged in"
- **Min transfer = 200 xu** (server rule)
- Mỗi session ~5-10 phút
- Bot sẽ fail khi quota video reward cạn (server returns "You can receive only 3") — cookies khác sẽ có quota mới

## Troubleshooting

### "Game frame not found"
- Cookies expired → refresh `ckN.txt`
- Hoặc FB block tạm → đợi 10-30 phút

### "WS not connected"
- Game load chưa xong — `find_gf` đã set max_wait=120s
- Restart loop

### "transfer fail: balance < 200"
- Account chưa đủ xu (mới tạo hoặc đã transfer hết)
- Bot sẽ claim tiếp để accumulate

### Log quá lớn
```bash
> loop.log  # truncate, giữ loop chạy tiếp
```
