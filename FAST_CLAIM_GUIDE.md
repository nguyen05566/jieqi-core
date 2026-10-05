# 🚀 Hướng Dẫn: Claim Nhanh Đạt 40 Claims + Transfer

## 🎯 Mục Tiêu

Bạn muốn **claim 40 lần nhanh nhất có thể** rồi **transfer 1 lần** thay vì chờ đợi giữa các claim.

---

## 📊 So Sánh Các Phương Án

| Phương Án | Tốc Độ | Rủi Ro | Mô Tả |
|-----------|--------|---------|-------|
| **ck1.py (gốc)** | Chậm | Thấp | 1 claim → đợi 3s → claim tiếp |
| **ck1_fast_40.py** | Nhanh | Trung bình | 40 claims liên tục (delay 0.5s) → transfer |
| **ck1_parallel_40.py** | Rất nhanh | Cao | 40 claims **song song** (threading) → transfer |

---

## 📁 Các File Đã Tạo

### 1. **ck1_fast_40.py** - Phương Án Nhanh (Khuyến Nghị) ⭐
- **Cơ chế**: Claim 40 lần liên tục với delay tối thiểu (0.5s)
- **Thời gian ước tính**: ~20-30 giây cho 40 claims
- **Rủi ro**: Thấp (vẫn tuân thủ rate limit cơ bản)
- **Cấu hình**:
  ```python
  MAX_CLAIMS = 40       # 40 claims mỗi session
  COOLDOWN = 0.5        # Chỉ đợi 0.5s giữa các claim
  TRANSFER_DEST_ID = 68307415
  ```

### 2. **ck1_parallel_40.py** - Phương Án Song Song (Cao Tốc)
- **Cơ chế**: Dùng threading để claim 40 lần **đồng thời**
- **Thời gian ước tính**: ~5-10 giây cho 40 claims
- **Rủi ro**: Cao (có thể bị Facebook phát hiện bot)
- **Cấu hình**:
  ```python
  MAX_CLAIMS = 40       # 40 claims song song
  COOLDOWN = 0.3        # Delay giữa các thread
  TRANSFER_DEST_ID = 68307415
  ```

---

## 🔧 Cách Sử Dụng

### Cài Đặt Thư Viện (nếu chưa có)

```bash
sudo pip3 install --break-system-packages playwright websocket-client
playwright install chromium
```

---

### Chạy ck1_fast_40.py (Khuyến Nghị)

```bash
# Cấu hình môi trường
export MAX_CLAIMS=40
export TRANSFER_DEST_ID=68307415
export COOLDOWN=0.5  # Delay giữa các claim (giây)
export HEADLESS=true
export REST_BETWEEN_RUNS=5
export MAX_RUNTIME=600  # 10 phút

# Chạy bot
python3 ck1_fast_40.py
```

**Dự kiến**: 40 claims trong ~20-30 giây, sau đó transfer.

---

### Chạy ck1_parallel_40.py (Cao Tốc)

```bash
# Cấu hình môi trường
export MAX_CLAIMS=40
export TRANSFER_DEST_ID=68307415
export COOLDOWN=0.3  # Delay giữa các thread
export HEADLESS=true
export REST_BETWEEN_RUNS=5
export MAX_RUNTIME=600

# Chạy bot
python3 ck1_parallel_40.py
```

**Dự kiến**: 40 claims song song trong ~5-10 giây, sau đó transfer.

---

## ⚙️ Cấu Hình Chi Tiết

### Biến Môi Trường

| Biến | Mặc Định | Mô Tả | Khuyến Nghị |
|------|----------|-------|--------------|
| `MAX_CLAIMS` | 40 | Số lần claim mỗi session | 40 |
| `TRANSFER_DEST_ID` | 68307415 | ID tài khoản nhận xu | 68307415 |
| `COOLDOWN` | 0.5 (fast) / 0.3 (parallel) | Delay giữa các claim (giây) | 0.5-1 |
| `HEADLESS` | true | Chạy ẩn (không mở trình duyệt) | true |
| `REST_BETWEEN_RUNS` | 5 | Nghỉ giữa các session (giây) | 5-10 |
| `MAX_RUNTIME` | 600 | Thời gian chạy tối đa (giây) | 600 (10 phút) |
| `TRANSFER_ENABLED` | true | Bật/tắt chức năng transfer | true |
| `PRE_CLAIM_TRANSFER_THRESHOLD` | 10000 | Ngưỡng xu để transfer trước | 10000 |

---

## 🎯 Cơ Chế Hoạt Động

### 1. ck1_fast_40.py (Nhanh)

```
Session 1:
├── Login
├── Check balance
├── Claim 1 → đợi 0.5s
├── Claim 2 → đợi 0.5s
├── ...
├── Claim 40 → đợi 0.5s
└── Transfer tất cả → Đóng

Thời gian: ~20-30 giây
```

### 2. ck1_parallel_40.py (Cao Tốc)

```
Session 1:
├── Login
├── Check balance
├── [Thread 1] Claim 1
├── [Thread 2] Claim 2
├── [Thread 3] Claim 3
├── ...
├── [Thread 40] Claim 40
└── Transfer tất cả → Đóng

Thời gian: ~5-10 giây
```

---

## ⚠️ Cảnh Báo & Lưu Ý

### ⚠️ Rủi Ro Của Phương Án Song Song

1. **Facebook có thể phát hiện bot**
   - Nhiều request đồng thời từ cùng 1 IP
   - Hành vi không giống người thật
   - **Khuyến nghị**: Chỉ dùng `ck1_fast_40.py` (không song song)

2. **Rate Limit**
   - Facebook có thể chặn IP nếu request quá nhanh
   - **Giải pháp**: Tăng `COOLDOWN` lên 1-2 giây

3. **Account Block**
   - Nếu account bị block, sẽ mất tất cả
   - **Giải pháp**: Dùng account test trước

### ✅ Phương Án An Toàn Nhất

```bash
# Dùng ck1_fast_40.py với delay an toàn
export MAX_CLAIMS=40
export COOLDOWN=1.0  # Đợi 1 giây giữa các claim
export TRANSFER_DEST_ID=68307415
python3 ck1_fast_40.py
```

---

## 📊 Thời Gian Dự Kiến

| Phương Án | Delay | Thời Gian 40 Claims | Rủi Ro |
|-----------|-------|---------------------|--------|
| ck1.py (gốc) | 3s | ~120 giây | ⭐ Thấp |
| ck1_fast_40.py | 0.5s | ~20-30 giây | ⭐⭐ Trung bình |
| ck1_fast_40.py | 1.0s | ~40 giây | ⭐ An toàn |
| ck1_parallel_40.py | 0.3s | ~5-10 giây | ⭐⭐⭐ Cao |

---

## 💡 Tips Tối Ưu

### 1. Tăng Dần Tốc Độ

Bắt đầu với delay cao, sau đó giảm dần:

```bash
# Lần 1: Delay 2s (an toàn)
export COOLDOWN=2.0
python3 ck1_fast_40.py

# Lần 2: Delay 1s (trung bình)
export COOLDOWN=1.0
python3 ck1_fast_40.py

# Lần 3: Delay 0.5s (nhanh)
export COOLDOWN=0.5
python3 ck1_fast_40.py
```

### 2. Chia Nhỏ Session

Thay vì 40 claims 1 lần, chia thành nhiều session nhỏ:

```bash
export MAX_CLAIMS=10  # 10 claims mỗi session
export REST_BETWEEN_RUNS=3  # Nghỉ 3s giữa các session
python3 ck1_fast_40.py
```

### 3. Theo Dõi Log

Kiểm tra log để thấy tốc độ thực tế:
```bash
# Chạy với HEADLESS=false để xem trình duyệt
python3 ck1_fast_40.py 2>&1 | tee claim_log.txt
```

---

## 🔄 So Sánh Với Bản Gốc (ck1.py)

| Đặc Điểm | ck1.py (gốc) | ck1_fast_40.py | ck1_parallel_40.py |
|----------|---------------|----------------|-------------------|
| Tốc độ | Chậm | Nhanh | Rất nhanh |
| Delay | 3s | 0.5s | 0.3s |
| Song song | ❌ Không | ❌ Không | ✅ Có |
| Rủi ro | ⭐ Thấp | ⭐⭐ Trung bình | ⭐⭐⭐ Cao |
| Thời gian 40 claims | ~120s | ~20-30s | ~5-10s |
| Khuyến nghị | ❌ | ✅ | ⚠️ (cẩn thận) |

---

## 🎯 Khuyến Nghị Cuối Cùng

1. **Bắt đầu với `ck1_fast_40.py`** - An toàn và hiệu quả
2. **Dùng `COOLDOWN=1.0`** - An toàn cho hầu hết trường hợp
3. **Theo dõi kết quả** - Điều chỉnh delay nếu cần
4. **Tránh song song** - Rủi ro cao, chỉ dùng nếu thực sự cần tốc độ

---

## 📞 Hỗ Trợ

Nếu gặp lỗi:
1. Kiểm tra cookie trong `ck1.txt`
2. Tăng `COOLDOWN` lên 2-3 giây
3. Chạy với `HEADLESS=false` để debug
4. Kiểm tra log để thấy lỗi cụ thể

---

## ✨ Kết Luận

Bạn có **3 lựa chọn** để đạt 40 claims nhanh:

1. **ck1_fast_40.py** (⭐ Khuyến nghị) - Nhanh và an toàn
2. **ck1.py với MAX_CLAIMS=40** - Chậm nhưng ổn định
3. **ck1_parallel_40.py** - Cao tốc nhưng rủi ro

**Lựa chọn tốt nhất cho hầu hết mọi người: `ck1_fast_40.py`**

---

## 🚀 Bắt Đầu Nào!

```bash
# Chạy phương án khuyến nghị
python3 ck1_fast_40.py
```

Chúc bạn claim thành công! 🎉
