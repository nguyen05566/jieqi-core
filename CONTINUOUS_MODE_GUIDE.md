# 🔄 Hướng Dẫn: CK1 Continuous Mode (Không Close/Reload)

## 🎯 Mục Tiêu

Bạn muốn **claim và transfer LIÊN TỤC** mà **KHÔNG cần**:
- ❌ Close browser
- ❌ Reload page
- ❌ Login lại Facebook
- ❌ Load game lại

**→ Giúp tiết kiệm thời gian, claim nhanh hơn**

---

## ✅ Giải Pháp: ck1_continuous.py

### 📝 Đặc Điểm

| Đặc Điểm | ck1.py (gốc) | ck1_continuous.py |
|----------|---------------|-------------------|
| Close browser sau session | ✅ Có | ❌ **Không** |
| Reload page | ✅ Có | ❌ **Không** |
| Login lại | ✅ Có | ❌ **Không** |
| Load game lại | ✅ Có | ❌ **Không** |
| Tốc độ | Chậm | **Nhanh hơn** |

### 🔄 Luồng Hoạt Động

```
1. Mở browser 1 lần
2. Login Facebook 1 lần
3. Load game 1 lần
4. WHILE thời gian chưa hết:
   ├─ Claim 1 lần
   ├─ Transfer về 68307415
   └─ Đợi COOLDOWN giây
5. Kết thúc → Close browser
```

**Không có bước close/reload/login giữa các claim!**

---

## 🚀 Cách Chạy

### 1. Cài Đặt Thư Viện (nếu chưa có)

```bash
sudo pip3 install --break-system-packages playwright websocket-client
playwright install chromium
```

### 2. Chạy Continuous Mode

```bash
# Cấu hình môi trường (tùy chọn)
export MAX_CLAIMS=1          # Mỗi lần claim 1 lần rồi transfer
export TRANSFER_DEST_ID=68307415
export COOLDOWN=3           # Đợi 3 giây giữa claim và transfer
export HEADLESS=true        # Chạy ẩn
export MAX_RUNTIME=600      # Chạy 10 phút

# Chạy bot
python3 ck1_continuous.py
```

---

## ⚙️ Cấu Hình Chi Tiết

### Biến Môi Trường

| Biến | Mặc Định | Mô Tả | Khuyến Nghị |
|------|----------|-------|--------------|
| `MAX_CLAIMS` | 1 | Số lần claim trước khi transfer | 1 (liên tục) |
| `TRANSFER_DEST_ID` | 68307415 | ID tài khoản nhận xu | 68307415 |
| `COOLDOWN` | 3 | Delay giữa claim và transfer (giây) | 2-5 |
| `HEADLESS` | true | Chạy ẩn (không mở trình duyệt) | true |
| `MAX_RUNTIME` | 600 | Thời gian chạy tối đa (giây) | 600 (10 phút) |
| `TRANSFER_ENABLED` | true | Bật/tắt chức năng transfer | true |
| `SINGLE_COOKIE_FILE` | ck1.txt | File cookie | ck1.txt |

---

## 📊 So Sánh Với Các Bản Khác

| Version | Close Browser | Reload | Login Lại | Tốc Độ | Rủi Ro |
|---------|---------------|--------|----------|--------|--------|
| ck1.py | ✅ Có | ✅ Có | ✅ Có | Chậm | ⭐ Thấp |
| ck1_fast_40.py | ✅ Có | ✅ Có | ✅ Có | Nhanh | ⭐⭐ Trung |
| ck1_parallel_40.py | ✅ Có | ✅ Có | ✅ Có | Rất nhanh | ⭐⭐⭐ Cao |
| **ck1_continuous.py** | ❌ **Không** | ❌ **Không** | ❌ **Không** | **Nhanh nhất** | ⭐⭐ Trung |

---

## 💡 Lợi Ích

### ✅ Ưu Điểm

1. **Tiết kiệm thời gian** - Không mất thời gian reload/login
2. **Nhanh hơn** - Claim và transfer liên tục
3. **Ít lỗi hơn** - Ít bước chuyển đổi giữa các session
4. **Dễ theo dõi** - Log liên tục, không bị đứt quãng

### ⚠️ Nhược Điểm

1. **Rủi ro cao hơn** - Nếu browser crash, mất tất cả
2. **Memory leak** - Browser chạy lâu có thể bị heavy
3. **Cookie hết hạn** - Nếu cookie hết hạn giữa chừng, phải chạy lại

---

## 🎯 Cấu Hình Tối Ưu

### An Toàn (Khuyến Nghị)

```bash
export COOLDOWN=3           # Đợi 3 giây giữa claim và transfer
export MAX_RUNTIME=600      # Chạy 10 phút
python3 ck1_continuous.py
```

### Nhanh Hơn

```bash
export COOLDOWN=1           # Đợi 1 giây
export MAX_RUNTIME=1800     # Chạy 30 phút
python3 ck1_continuous.py
```

### Rất Nhanh (Cẩn Thận)

```bash
export COOLDOWN=0.5         # Đợi 0.5 giây
export MAX_RUNTIME=600      # Chạy 10 phút
python3 ck1_continuous.py
```

---

## ⚠️ Cảnh Báo

1. **Nếu browser crash** - Bạn sẽ mất tất cả tiến độ
2. **Nếu cookie hết hạn** - Bot sẽ dừng hoạt động
3. **Nếu bị block** - Account có thể bị khóa
4. **Memory usage** - Browser chạy lâu có thể ngốn nhiều RAM

**Khuyến nghị**: Chạy thử với `MAX_RUNTIME=60` (1 phút) trước

---

## 🐛 Khắc Phục Lỗi

### Lỗi: Browser Crash
**Nguyên nhân**: Chạy quá lâu, memory leak
**Giải pháp**: Giảm `MAX_RUNTIME`, chạy nhiều lần ngắn

### Lỗi: Cookie Hết Hạn
**Nguyên nhân**: Cookie Facebook hết hạn
**Giải pháp**: Lấy cookie mới, thay vào `ck1.txt`

### Lỗi: WS Not Connected
**Nguyên nhân**: WebSocket bị disconnect
**Giải pháp**: Bot sẽ tự reconnect, nếu fail nhiều lần sẽ dừng

### Lỗi: Account Blocked
**Nguyên nhân**: Facebook phát hiện bot
**Giải pháp**: Giảm `COOLDOWN`, dùng account khác

---

## 📚 Tài Liệu Liên Quan

- `FAST_CLAIM_GUIDE.md` - Hướng dẫn claim nhanh 40 lần
- `CK1_MODIFICATIONS.md` - Thay đổi ban đầu
- `ck1.py` - Bản gốc
- `ck1_fast_40.py` - Claim 40 lần nhanh
- `ck1_parallel_40.py` - Claim song song

---

## ✨ Kết Luận

**ck1_continuous.py** là lựa chọn tốt nhất nếu bạn muốn:
- ✅ Claim và transfer liên tục
- ✅ Không mất thời gian reload/login
- ✅ Tốc độ nhanh
- ✅ Dễ sử dụng

**Bắt đầu ngay:**
```bash
python3 ck1_continuous.py
```

Chúc bạn claim thành công! 🎉
