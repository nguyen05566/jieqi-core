#!/usr/bin/env python3
"""
FB Tien Len Mien Nam reward bot v12 — AUTO-CLICK PLAY & ULTRA ROBUST RECOVERY
Nâng cấp cốt lõi:
- Xử lý lỗi không tìm thấy Frame do vướng màn hình chờ "Play Game" của FB.
- Cải tiến cơ chế dò Frame linh hoạt, không sleep tĩnh.
- Tự động bắt lại Frame liên tục khi mất kết nối WebSocket.
"""

import os, sys, time, random

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import anti_lock as al
except Exception as e:
    print(f"[WARN] Không nạp được anti_lock.py — chạy chế độ cũ: {e}", flush=True)
    al = None

from playwright.sync_api import sync_playwright

# ============================================================
# CONFIG
# ============================================================
GAME_URL = "https://www.facebook.com/gaming/play/tienlen_miennam"

CLAIM_BATCH   = int(os.environ.get("CLAIM_BATCH", "40"))
DELAY         = float(os.environ.get("COOLDOWN", "3"))
REST          = int(os.environ.get("REST_BETWEEN_RUNS", "30"))
MAX_RUNTIME   = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS      = os.environ.get("HEADLESS", "true").lower() == "true"

TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "51977054"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"
PRE_CLAIM_TRANSFER_THRESHOLD = int(os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000"))

SINGLE_COOKIE_FILE = os.environ.get("SINGLE_COOKIE_FILE", "ck1.txt").strip()

MAX_SESSIONS            = int(os.environ.get("MAX_SESSIONS", "12"))
MAX_RELOADS_PER_SESSION = int(os.environ.get("MAX_RELOADS", "8"))
MAX_RECOVER_FAIL        = int(os.environ.get("MAX_RECOVER_FAIL", "3"))
RELOAD_COOLDOWN         = int(os.environ.get("RELOAD_COOLDOWN", "45"))
FRAME_WAIT              = int(os.environ.get("FRAME_WAIT", "90"))
WS_WAIT                 = int(os.environ.get("WS_WAIT", "60"))
MAX_CONSEC_CLAIM_FAIL   = int(os.environ.get("MAX_CONSEC_CLAIM_FAIL", "6"))
MIN_TIME_LEFT           = 90

MAX_CLAIMS_PER_DAY         = int(os.environ.get("MAX_CLAIMS_PER_DAY", str(getattr(al, "DEFAULT_MAX_CLAIMS_PER_DAY", 180) if al else 180)))
MAX_TRANSFERS_PER_DAY      = int(os.environ.get("MAX_TRANSFERS_PER_DAY", str(getattr(al, "DEFAULT_MAX_TRANSFERS_PER_DAY", 30) if al else 30)))
MAX_TRANSFER_AMOUNT_PER_DAY = int(os.environ.get("MAX_TRANSFER_AMOUNT_PER_DAY", str(getattr(al, "DEFAULT_MAX_TRANSFER_AMOUNT", 2_000_000) if al else 2_000_000)))

SESSION_START_JITTER = int(os.environ.get("SESSION_START_JITTER", "180"))
IDLE_EVERY_CLAIMS    = int(os.environ.get("IDLE_EVERY_CLAIMS", "60"))
WARMUP_ENABLED       = os.environ.get("WARMUP_ENABLED", "true").lower() == "true"

FRAME_ERR_HINTS = (
    "detach", "execution context", "target closed", "has been closed",
    "frame was", "navigation", "page closed", "browser has been closed",
    "connection closed", "context destroyed"
)

def log(msg=""): print(msg, flush=True)

def is_frame_error(err_text: str) -> bool:
    t = (err_text or "").lower()
    return any(h in t for h in FRAME_ERR_HINTS)

class SessionDead(Exception): pass

# ============================================================
# COOKIE & UTILS
# ============================================================
def load_single_cookie_set(path):
    if not os.path.exists(path):
        log(f"[COOKIE] ❌ Không tìm thấy file: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
    except Exception as e:
        log(f"[COOKIE] ❌ Lỗi đọc {path}: {e}")
        return []
    if not content: return []
    content = " ".join(content.strip('"').strip("'").split()).replace(";  ", "; ").replace(" ;", ";")
    log(f"[COOKIE] ✅ Nạp {os.path.basename(path)} ({len(content)} ký tự)")
    return [{"file": os.path.basename(path), "raw": content}]

def parse_cookie(raw: str):
    raw = " ".join(raw.strip().strip('"').strip("'").split()).replace(";  ", "; ").replace(" ;", ";")
    out = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part: continue
        n, v = part.split("=", 1)
        if n.strip() and v.strip():
            out.append({"name": n.strip(), "value": v.strip(), "domain": ".facebook.com",
                        "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"})
    return out

def parse_balance_num(bal_text):
    if not bal_text or bal_text == "?": return 0
    s = "".join(ch for ch in str(bal_text).strip().lower() if ch.isdigit() or ch in ".km")
    try:
        if s.endswith("k"): return int(float(s[:-1]) * 1000)
        if s.endswith("m"): return int(float(s[:-1]) * 1000000)
        return int(float(s))
    except Exception: return 0

# ============================================================
# GAME SESSION - NÂNG CẤP XỬ LÝ FRAME & KẾT NỐI
# ============================================================
class GameSession:
    def __init__(self, page, started_at):
        self.page = page
        self.started_at = started_at
        self.gf = None
        self.reloads = 0
        self.recover_fail = 0
        self.last_reload_ts = 0.0

    def time_left(self): return MAX_RUNTIME - (time.time() - self.started_at)

    def check_time(self):
        if self.time_left() <= MIN_TIME_LEFT: raise SessionDead("Hết thời gian MAX_RUNTIME")

    def _frame_alive(self, f):
        if not f: return False
        try:
            if f.is_detached(): return False
            # Dùng await lỏng lẻo để tránh bị block mãi mãi nếu context lag
            return bool(f.evaluate("() => typeof window !== 'undefined'"))
        except Exception: return False

    def _click_fb_play_button(self):
        """Tự động bấm nút 'Chơi' / 'Play' của màn hình chờ Facebook (nếu có)."""
        try:
            # Script tìm nút div có chữ 'Chơi' hoặc 'Play' và click nó trên Main Page
            self.page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('div[role="button"]'));
                for (const b of btns) {
                    const txt = (b.innerText || '').toLowerCase();
                    if (txt === 'chơi' || txt === 'chơi ngay' || txt === 'play game' || txt === 'play') {
                        b.click(); return true;
                    }
                }
                return false;
            }""")
        except Exception:
            pass

    def _scan_frames(self):
        try: frames = list(self.page.frames)
        except Exception: return None
        
        # Chiến lược 1: Tìm theo URL (Mở rộng từ khóa)
        for f in frames:
            try:
                if f.is_detached(): continue
                url = (f.url or "").lower()
                if "instant-bundle" in url or "fbsbx.com" in url or "fbcdn.net" in url:
                    if self._frame_alive(f): return f
            except Exception: continue
            
        # Chiến lược 2: Tìm bằng đặc điểm của biến Javascript trong Frame
        for f in frames:
            try:
                if f.is_detached(): continue
                ok = f.evaluate("() => typeof window !== 'undefined' && !!(window.connection || document.querySelector('.chipBalance') || typeof window.createTable === 'function')")
                if ok: return f
            except Exception: continue
            
        return None

    def find_frame(self, max_wait=FRAME_WAIT, verbose=True):
        """Liên tục tìm Frame, kết hợp tự động bấm nút Play nếu bị vướng."""
        deadline = time.time() + max_wait
        last_click_try = 0
        
        while time.time() < deadline:
            if self.page.is_closed(): raise SessionDead("Page đã bị đóng")
            
            # Mỗi 5 giây thử click nút "Chơi" 1 lần nếu bị màn hình chờ chặn
            if time.time() - last_click_try > 5:
                self._click_fb_play_button()
                last_click_try = time.time()

            f = self._scan_frames()
            if f:
                self.gf = f
                if verbose: log("  ✓ Tìm thấy game frame")
                return f
                
            time.sleep(2) # Polling thay vì sleep tĩnh
            
        if verbose: log(f"  ⚠ Không thấy game frame sau {max_wait}s")
        return None

    def frame(self, quick=True):
        if self._frame_alive(self.gf): return self.gf
        self.gf = None # Clear cached dead frame
        # Quét nhanh 8s nếu frame cũ vừa chết
        return self.find_frame(max_wait=8 if quick else FRAME_WAIT, verbose=False)

    def eval(self, js, arg=None, default=None, retries=1):
        for attempt in range(retries + 1):
            if self.page.is_closed(): raise SessionDead("Page đã bị đóng")
            f = self.frame()
            if not f:
                if attempt < retries: time.sleep(2); continue
                return default
            try: 
                return f.evaluate(js, arg)
            except Exception as e:
                # Nếu văng lỗi Context Destroyed -> Hủy cache frame hiện tại để lần lặp sau tự dò lại frame mới
                if is_frame_error(str(e)): 
                    self.gf = None
                if attempt < retries: time.sleep(1.5); continue
                return default
        return default

    def ws_ok(self):
        return bool(self.eval("() => !!(window.connection && connection.ws && connection.ws.readyState === 1)", default=False, retries=0))

    def wait_ws(self, max_wait=WS_WAIT):
        deadline = time.time() + max_wait
        while time.time() < deadline:
            if self.page.is_closed(): raise SessionDead("Page đóng khi chờ WS")
            if self.ws_ok(): return True
            # Dò lại frame nếu trong lúc chờ frame bị swap/detach
            if not self._frame_alive(self.gf):
                self.gf = None
            time.sleep(3)
        return False

    def check_page_health(self):
        if self.page.is_closed(): raise SessionDead("Page đã bị đóng")
        try: url = (self.page.url or "").lower()
        except Exception: raise SessionDead("Không đọc được page.url")
        if "checkpoint" in url or "/login" in url or "login.php" in url:
            raise SessionDead(f"Bị logout/checkpoint ({url[:80]})")
        try:
            if self.page.locator('input[name="pass"], input[placeholder="Email or phone"]').count() > 0:
                raise SessionDead("Hiện form đăng nhập -> cookie chết")
        except SessionDead: raise
        except Exception: pass

    def recover(self, reason=""):
        self.check_time()
        self.check_page_health()
        if self.reloads >= MAX_RELOADS_PER_SESSION: raise SessionDead(f"Vượt quá {MAX_RELOADS_PER_SESSION} lần reload")
        if self.recover_fail >= MAX_RECOVER_FAIL: raise SessionDead(f"Recover thất bại {self.recover_fail} lần liên tiếp")

        since = time.time() - self.last_reload_ts
        if self.last_reload_ts and since < RELOAD_COOLDOWN:
            w = RELOAD_COOLDOWN - since
            if w > self.time_left() - MIN_TIME_LEFT: raise SessionDead("Không đủ thời gian cho cooldown reload")
            log(f"  ⏳ Cooldown reload: chờ {w:.0f}s")
            time.sleep(w)

        self.reloads += 1
        self.last_reload_ts = time.time()
        hard = (self.reloads % 2 == 0)
        log(f"  🔄 RECOVER #{self.reloads}/{MAX_RELOADS_PER_SESSION} ({'goto' if hard else 'reload'}) — {reason}")

        self.gf = None
        try:
            if hard: self.page.goto(GAME_URL, wait_until="domcontentloaded", timeout=60000)
            else: self.page.reload(wait_until="domcontentloaded", timeout=60000)
            # Không sleep 15s cứng ngắc nữa, chờ 3s rồi nhảy vào find_frame ngay
            time.sleep(3)
        except Exception as e:
            if "closed" in str(e).lower() or "crash" in str(e).lower(): raise SessionDead("Page crash/closed khi navigate")
            self.recover_fail += 1
            if self.recover_fail >= MAX_RECOVER_FAIL: raise SessionDead("Navigate liên tục thất bại")
            return False

        self.check_page_health()
        
        # find_frame đã tích hợp auto-click "Chơi" và chờ linh hoạt 90s
        if not self.find_frame(max_wait=FRAME_WAIT, verbose=True):
            self.recover_fail += 1
            log(f"  ❌ Recover fail: không thấy game frame (Có thể vướng lỗi UI FB)")
            if self.recover_fail >= MAX_RECOVER_FAIL: raise SessionDead("Không tìm được game frame")
            return False

        if not self.wait_ws(WS_WAIT):
            self.recover_fail += 1
            log(f"  ❌ Recover fail: WS không kết nối (Game bảo trì hoặc lag server)")
            if self.recover_fail >= MAX_RECOVER_FAIL: raise SessionDead("WS không kết nối")
            return False

        self.recover_fail = 0
        log("  ✅ RECOVER OK — Frame + WS đã sống lại")
        return True

    def ensure_ready(self, reason="check", attempts=2):
        if self.frame() and self.ws_ok(): return True
        log(f"  ⚠ Kết nối lỗi ({reason}) -> Bắt đầu quá trình khôi phục...")
        for i in range(attempts):
            if self.recover(reason=f"Thử lại lần {i+1}"): return True
        return self.frame() is not None and self.ws_ok()

    def close_dialogs(self):
        self.eval("() => { try { $('.msgBoxBackGround,.msgBox').remove(); } catch(e) {} }", retries=0)

    def get_bal(self):
        return self.eval("() => document.querySelector('.chipBalance')?.textContent.trim() || '?'", default="?", retries=0)

    def is_account_blocked(self):
        return bool(self.eval("""() => {
            const dialogs = document.querySelectorAll('[class*="msgBox"], [class*="dialog"], [class*="alert"]');
            for (const d of dialogs) {
                if (d.offsetParent === null) continue;
                const txt = (d.textContent || '').toLowerCase();
                if (txt.includes('blocked') || txt.includes('khóa') || txt.includes('cấm')) return true;
            }
            return false;
        }""", default=False, retries=0))

# ============================================================
# JS PAYLOADS
# ============================================================
JS_TRANSFER = """(destId) => new Promise((resolve) => {
    try {
        const balText = document.querySelector('.chipBalance')?.textContent.trim() || '0';
        let balance = 0;
        const cleaned = balText.replace(/[^0-9kK.]/g, '');
        if (cleaned.toLowerCase().endsWith('k')) balance = Math.round(parseFloat(cleaned.slice(0, -1)) * 1000);
        else if (cleaned) balance = parseInt(cleaned) || 0;
        if (balance < 200) { resolve({success:false, error:'balance < 200', balance}); return; }
        if (!window.connection || !connection.ws || connection.ws.readyState !== 1) { resolve({success:false, error:'ws not connected', balance}); return; }
        
        const msg = new OutboundMessage("TRANSFER");
        msg.writeLong(destId); msg.writeLong(balance);
        let resolved = false;
        connection.send(msg, (resp, ok) => {
            if (resolved) return; resolved = true;
            try {
                resolve({success:ok, status:resp.readSignedByte(), message:resp.readUtf16String ? resp.readUtf16String() : '', balance, dest:destId});
            } catch(e) { resolve({success:ok, error:e.toString(), balance}); }
        });
        setTimeout(() => { if(!resolved){ resolved=true; resolve({success:false, error:'timeout', balance}); } }, 12000);
    } catch(e) { resolve({success:false, error:e.toString()}); }
})"""

JS_CLAIM = """(timeoutMs) => new Promise((resolve) => {
    try {
        if (!window.connection || !connection.ws || connection.ws.readyState !== 1) { resolve({success:false, error:'ws not connected'}); return; }
        const msg = new OutboundMessage("VIDEO_REWARD");
        msg.writeByte(1);
        let resolved = false;
        connection.send(msg, (response, success) => {
            if (resolved) return; resolved = true;
            if (success) {
                try {
                    const amount = response.readLong();
                    if (window.Ads && window.Ads.RewardedVideo) {
                        window.Ads.RewardedVideo.videoIndex++;
                        if (window.Ads.RewardedVideo.updateRewardButton) window.Ads.RewardedVideo.updateRewardButton();
                    }
                    resolve({success:true, amount});
                } catch(e) { resolve({success:true, amount:0, error:e.toString()}); }
            } else resolve({success:false, error:'no response'});
        });
        setTimeout(() => { if(!resolved){ resolved=true; resolve({success:false, error:'timeout'}); } }, timeoutMs);
    } catch(e) { resolve({success:false, error:e.toString()}); }
})"""

JS_CLICK_WATCH = """() => {
    const dialogs = document.querySelectorAll('[class*="msgBox"]');
    for (const d of dialogs) {
        if (d.offsetParent !== null && (d.textContent || '').includes('enough coin')) {
            for (const b of d.querySelectorAll('input[type="button"], button')) {
                const val = (b.value || b.textContent || '').toLowerCase();
                if (val.includes('watch') || val.includes('video')) { b.click(); return true; }
            }
        }
    }
    return false;
}"""

# ============================================================
# ACTIONS
# ============================================================
def transfer_all_xu(s: GameSession, dest_id=TRANSFER_DEST_ID):
    if not s.ensure_ready("transfer"): return {"success": False, "error": "Session chưa sẵn sàng"}
    res = s.eval(JS_TRANSFER, dest_id, default=None, retries=1)
    return res if res else {"success": False, "error": "evaluate failed"}

def trigger_and_claim(s: GameSession):
    if not s.ensure_ready("chuẩn bị claim"): return {"success": False, "error": "Session chưa sẵn sàng"}
    s.eval("() => { try { createTable(); } catch(e) {} }", retries=0)
    time.sleep(2)
    s.eval("() => { const r = document.getElementById('radio_11'); if(r) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true})); } }", retries=0)
    time.sleep(0.5)
    s.eval("() => { const b = document.querySelector('input[name=\"CREATE\"]'); if(b) b.click(); }", retries=0)
    time.sleep(3)

    alert_clicked = bool(s.eval(JS_CLICK_WATCH, default=False, retries=0))
    if alert_clicked: time.sleep(2)

    result = None
    for attempt in range(2):
        result = s.eval(JS_CLAIM, 15000, default={"success": False, "error": "evaluate failed"}, retries=0)
        if isinstance(result, dict) and result.get("success") and result.get("amount", 0) > 0: break
        
        err = result.get("error", "unknown") if isinstance(result, dict) else "bad result"
        if attempt == 0:
            log(f"    attempt {attempt+1}/2: FAIL ({err}) — mồi lại lệnh claim")
            s.close_dialogs()
            time.sleep(2)
            if not (s.frame() and s.ws_ok()) and not s.ensure_ready("claim-retry", attempts=1): break
            s.eval(JS_CLICK_WATCH, default=False, retries=0)
            time.sleep(1)

    if not isinstance(result, dict): result = {"success": False, "error": "bad result"}
    if not result.get("success") or result.get("amount", 0) == 0:
        result["method"] = "alert_clicked" if alert_clicked else "no_alert"
    return result

# ============================================================
# SESSION LOOP
# ============================================================
def run_session(p, fb_cookies, session_id, started_at):
    log(f"\n########## SESSION {session_id} ##########")
    browser = context = page = None
    total_reward = total_transferred = ok = fail_total = 0
    cookie_ok = True

    try:
        fp = al.get_or_create_fingerprint(SINGLE_COOKIE_FILE) if al else None
        if fp: log(f"[ANTI-BAN] UA={fp['user_agent'][:50]}... locale={fp['locale']}")
        else: log("[ANTI-BAN] Module anti_lock không khả dụng.")

        browser = p.chromium.launch(headless=HEADLESS, args=al.stealth_launch_args() if al else ["--no-sandbox"])
        
        ctx_args = {}
        if fp:
            ctx_args.update({"viewport": fp["viewport"], "locale": fp["locale"], "user_agent": fp["user_agent"], "timezone_id": fp["timezone"]})
        context = browser.new_context(**{k: v for k, v in ctx_args.items() if v is not None})

        if al and fp:
            try: context.add_init_script(al.build_stealth_js(fp))
            except Exception as e: log(f"[ANTI-BAN] Stealth JS fail: {e}")

        cookies_list = [dict(c, domain=".facebook.com") for c in fb_cookies]
        context.add_cookies(cookies_list)

        page = context.new_page()
        page.set_default_timeout(45000)
        s = GameSession(page, started_at)

        log("[1] Login FB...")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
        s.check_page_health()

        if WARMUP_ENABLED and al: al.warm_up_account(page, max_s=15)

        log("[2] Open game...")
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=60000)
        
        # Bắt đầu tự dò frame và click Play (nếu có)
        if not s.find_frame(max_wait=FRAME_WAIT):
            log("  ⚠ Chưa thấy game frame — recover 1 lần")
            s.recover("Khởi động không thấy frame")

        log("[3] Wait WS...")
        if not s.wait_ws(WS_WAIT) and not s.ensure_ready("WS khởi động"):
            return 0, 0, 0, 0, True

        if s.is_account_blocked():
            log("  ❌ ACCOUNT BLOCKED — dừng")
            return 0, 0, 0, 0, False

        log(f"  Balance Start: {s.get_bal()}")

        if al:
            ok_quota, reason = al.check_daily_quota(SINGLE_COOKIE_FILE)
            if not ok_quota:
                log(f"  ⏸ [ANTI-BAN] Bỏ qua: {reason}")
                return 0, 0, 0, 0, True
            al.record_session_start(SINGLE_COOKIE_FILE)

        claim_count = batch_no = consec_fail = 0
        dest_id = TRANSFER_DEST_ID

        log(f"\n[4] BATCH MODE: ~{CLAIM_BATCH} -> transfer")
        while True:
            if s.time_left() <= MIN_TIME_LEFT: break
            batch_no += 1
            cur_batch = al.random_batch_size(CLAIM_BATCH, lo=max(10, CLAIM_BATCH-5), hi=CLAIM_BATCH+5) if al else CLAIM_BATCH

            bal_num = parse_balance_num(s.get_bal())
            if TRANSFER_ENABLED and bal_num > PRE_CLAIM_TRANSFER_THRESHOLD:
                log(f"\n[Pre-batch] {bal_num:,} > {PRE_CLAIM_TRANSFER_THRESHOLD:,} -> Transfer")
                r = transfer_all_xu(s, dest_id)
                if r.get("success"):
                    amt = r.get("balance", 0)
                    total_transferred += amt
                    log(f"  ✅ Chuyển {amt:,} -> {dest_id}")
                    if al:
                        if al.detect_soft_ban(r.get("message", "")) or al.detect_soft_ban(r.get("error", "")):
                            al.set_soft_ban(SINGLE_COOKIE_FILE)
                            return total_reward, total_transferred, ok, fail_total, True
                        al.record_transfer(SINGLE_COOKIE_FILE, amt)
                    time.sleep(2)

            log(f"\n[Batch #{batch_no}] {cur_batch} claims...")
            stop_session = False
            for i in range(cur_batch):
                if s.time_left() <= MIN_TIME_LEFT: stop_session = True; break
                
                log(f"  [Claim #{claim_count+1}] Balance: {s.get_bal()} -> claiming...")
                s.close_dialogs()
                al.jitter_sleep(1.0, 1.0) if al else time.sleep(1)

                result = trigger_and_claim(s)

                if al and (al.detect_soft_ban(result.get("error", "")) or al.detect_soft_ban(result.get("message", ""))):
                    log("  🚫 [ANTI-BAN] Soft-ban detected -> back-off 15m")
                    al.set_soft_ban(SINGLE_COOKIE_FILE)
                    return total_reward, total_transferred, ok, fail_total, True

                if result.get("success") and result.get("amount", 0) > 0:
                    amount = result["amount"]
                    total_reward += amount; ok += 1; claim_count += 1; consec_fail = 0
                    if al: al.record_claim(SINGLE_COOKIE_FILE, amount)
                    al.jitter_sleep(1.0, 0.8) if al else time.sleep(1)
                    log(f"    ✅ OK +{amount} | {s.get_bal()} | Total: {total_reward:,}")
                    if al and IDLE_EVERY_CLAIMS > 0: al.maybe_idle_browse(page, claim_count, every=IDLE_EVERY_CLAIMS)
                else:
                    fail_total += 1; consec_fail += 1
                    log(f"    ❌ FAIL ({result.get('error', 'unknown')}) | Liên tiếp: {consec_fail}")
                    
                    if parse_balance_num(s.get_bal()) >= 50000:
                        log("  💸 Balance >= 50k — Game chặn claim, ép TRANSFER")
                        break
                    
                    if consec_fail >= MAX_CONSEC_CLAIM_FAIL:
                        log(f"  ⚠ {consec_fail} fail liên tiếp -> Gọi khôi phục")
                        if not s.ensure_ready("Nhiều claim fail", attempts=1): stop_session = True; break
                        consec_fail = 0

                al.human_delay(max(2.0, DELAY), max(4.0, DELAY+3.0)) if al else time.sleep(DELAY + random.uniform(0, 1.5))

            if TRANSFER_ENABLED and parse_balance_num(s.get_bal()) > 200:
                log(f"\n[Transfer] Chuyển về {dest_id}...")
                r = transfer_all_xu(s, dest_id)
                if r.get("success"):
                    amt = r.get("balance", 0)
                    total_transferred += amt
                    log(f"  ✅ Đã chuyển {amt:,} -> {dest_id}")
                    if al:
                        if al.detect_soft_ban(r.get("message", "")) or al.detect_soft_ban(r.get("error", "")):
                            al.set_soft_ban(SINGLE_COOKIE_FILE)
                            return total_reward, total_transferred, ok, fail_total, True
                        al.record_transfer(SINGLE_COOKIE_FILE, amt)
                else:
                    log(f"  ❌ Transfer FAIL: {r.get('error', 'unknown')}")
            if stop_session: break
            al.human_delay(max(3.0, DELAY), max(8.0, DELAY+5.0)) if al else time.sleep(DELAY)

    except SessionDead as e:
        log(f"\n[SESSION {session_id}] 💀 DEAD: {e}")
        if "cookie chết" in str(e) or "logout" in str(e) or "checkpoint" in str(e): cookie_ok = False
    except Exception as e: log(f"\n[SESSION {session_id}] ⚠ Lỗi: {type(e).__name__}: {str(e)[:160]}")
    finally:
        # Tối ưu tránh tràn RAM
        if page:
            try: page.close()
            except: pass
        if context:
            try: context.close()
            except: pass
        if browser:
            try: browser.close(); log("  🧹 Đã dọn dẹp Browser an toàn")
            except: pass

    log(f"[SESSION {session_id}] OK={ok} | fail={fail_total} | reward={total_reward:,} | transfer={total_transferred:,}")
    return total_reward, total_transferred, ok, fail_total, cookie_ok

# ============================================================
# MAIN
# ============================================================
def main():
    log("=" * 64)
    log("FB Tien Len Mien Nam bot v12 — VƯỢT SPLASH SCREEN FB + ROBUST WS")
    log("=" * 64)
    
    cookies = load_single_cookie_set(SINGLE_COOKIE_FILE)
    if not cookies: return 1
    fb_cookies = parse_cookie(cookies[0]["raw"])
    if not fb_cookies: log("[STOP] Cookie parse lỗi."); return 1

    if al:
        ok_q, reason = al.check_daily_quota(SINGLE_COOKIE_FILE)
        if not ok_q: log(f"\n[ANTI-BAN] ⏸ Dừng: {reason}"); return 0
        if SESSION_START_JITTER > 0:
            log(f"\n[ANTI-BAN] ⏳ Jitter: Đang nghỉ trước khi chạy...")
            al.random_session_offset(SESSION_START_JITTER)

    started_at = time.time()
    session_id, grand_reward, grand_transfer, grand_ok, grand_fail = 0, 0, 0, 0, 0

    with sync_playwright() as p:
        while session_id < MAX_SESSIONS:
            left = MAX_RUNTIME - (time.time() - started_at)
            if left <= MIN_TIME_LEFT: break

            session_id += 1
            log(f"\n{'=' * 64}\n[Session {session_id}/{MAX_SESSIONS}] {time.strftime('%H:%M:%S')} | Còn {int(left)}s\n{'=' * 64}")
            
            rw, tr, ok, fail, cookie_ok = run_session(p, fb_cookies, session_id, started_at)
            grand_reward += rw; grand_transfer += tr; grand_ok += ok; grand_fail += fail
            
            log(f"\n[Tổng] OK={grand_ok} fail={grand_fail} | reward={grand_reward:,} | transfer={grand_transfer:,}")
            if not cookie_ok: log("[STOP] Cookie hỏng."); break

            left = MAX_RUNTIME - (time.time() - started_at)
            if left <= MIN_TIME_LEFT: break
            if session_id < MAX_SESSIONS:
                wait = min(REST, max(5, int(left - MIN_TIME_LEFT)))
                log(f"\n💤 Nghỉ {wait}s...")
                time.sleep(wait)

    log(f"\n{'=' * 64}\nTỔNG KẾT: {session_id} ss | {grand_ok} OK | {grand_fail} fail | rw={grand_reward:,} | tr={grand_transfer:,}\n{'=' * 64}")
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt: log("\n[EXIT] Stop."); sys.exit(130)
