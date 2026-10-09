```python
#!/usr/bin/env python3
"""
FB Tien Len Mien Nam reward bot v13 — SELF-CONTAINED SINGLE FILE
Gộp toàn bộ anti_lock.py và ck1.py vào chung 1 file duy nhất.
Tích hợp: Chống bot (Stealth JS), Quota hàng ngày, Quản lý Fingerprint,
Auto-click màn hình chờ, Batch Claim & Transfer, Quản lý tài nguyên tránh tràn RAM.
"""

import os
import sys
import time
import random
import json

from playwright.sync_api import sync_playwright

# ============================================================
# CONFIGURATION & ENVIRONMENT
# ============================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
FP_DIR        = os.environ.get("FP_DIR", os.path.join(_HERE, "fingerprints"))
STATE_DIR     = os.environ.get("STATE_DIR", os.path.join(_HERE, "state"))
DEST_FILE     = os.environ.get("TRANSFER_DEST_FILE", os.path.join(_HERE, "transfer_dests.json"))

GAME_URL = "https://www.facebook.com/gaming/play/tienlen_miennam"

CLAIM_BATCH   = int(os.environ.get("CLAIM_BATCH", "40"))
DELAY         = float(os.environ.get("COOLDOWN", "3"))
REST          = int(os.environ.get("REST_BETWEEN_RUNS", "30"))
MAX_RUNTIME   = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS      = os.environ.get("HEADLESS", "true").lower() == "true"

TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "51977054"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"
PRE_CLAIM_TRANSFER_THRESHOLD = int(os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000"))

SINGLE_COOKIE_FILE = os.environ.get("SINGLE_COOKIE_FILE", "ck14.txt").strip()

MAX_SESSIONS            = int(os.environ.get("MAX_SESSIONS", "12"))
MAX_RELOADS_PER_SESSION = int(os.environ.get("MAX_RELOADS", "8"))
MAX_RECOVER_FAIL        = int(os.environ.get("MAX_RECOVER_FAIL", "3"))
RELOAD_COOLDOWN         = int(os.environ.get("RELOAD_COOLDOWN", "45"))
FRAME_WAIT              = int(os.environ.get("FRAME_WAIT", "90"))
WS_WAIT                 = int(os.environ.get("WS_WAIT", "60"))
MAX_CONSEC_CLAIM_FAIL   = int(os.environ.get("MAX_CONSEC_CLAIM_FAIL", "6"))
MIN_TIME_LEFT           = 90

DEFAULT_MAX_CLAIMS_PER_DAY    = int(os.environ.get("MAX_CLAIMS_PER_DAY", "180"))
DEFAULT_MAX_TRANSFERS_PER_DAY = int(os.environ.get("MAX_TRANSFERS_PER_DAY", "30"))
DEFAULT_MAX_TRANSFER_AMOUNT   = int(os.environ.get("MAX_TRANSFER_AMOUNT_PER_DAY", "2000000"))

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
# ANTI-BAN & FINGERPRINT MODULE (Nhúng trực tiếp)
# ============================================================
def _safe_read_json(path: str, default=None):
    if default is None: default = {}
    if not os.path.exists(path): return default
    for _ in range(5):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            time.sleep(random.uniform(0.1, 0.5))
    return default

def _safe_write_json(path: str, data: dict):
    for _ in range(5):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            return True
        except Exception:
            time.sleep(random.uniform(0.1, 0.5))
    return False

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080}, {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},  {"width": 1366, "height": 768},
]

LOCALES = ["vi-VN", "en-US"]
TIMEZONES = ["Asia/Ho_Chi_Minh", "Asia/Bangkok"]

WEBGL_VENDORS = [
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.1)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060, OpenGL 4.5)"),
]

def get_or_create_fingerprint(cookie_file: str) -> dict:
    os.makedirs(FP_DIR, exist_ok=True)
    fp_path = os.path.join(FP_DIR, "fingerprint.json")
    fingerprints = _safe_read_json(fp_path)
    key = os.path.basename(cookie_file)

    if key not in fingerprints:
        ua = random.choice(USER_AGENTS)
        vendor, renderer = random.choice(WEBGL_VENDORS)
        fingerprints[key] = {
            "user_agent": ua,
            "viewport": random.choice(VIEWPORTS),
            "locale": random.choice(LOCALES),
            "timezone": random.choice(TIMEZONES),
            "platform": "Win32" if "Windows" in ua else "MacIntel",
            "webgl_vendor": vendor,
            "webgl_renderer": renderer,
            "hardware_concurrency": random.choice([4, 8, 16]),
            "device_memory": random.choice([8, 16]),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _safe_write_json(fp_path, fingerprints)
    return fingerprints[key]

def build_stealth_js(fp: dict) -> str:
    return f"""(() => {{
    try {{
        Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
        delete navigator.__proto__.webdriver;
        Object.defineProperty(navigator, 'platform', {{get: () => '{fp["platform"]}'}});
        Object.defineProperty(navigator, 'languages', {{get: () => ['{fp["locale"]}', 'en']}});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {fp["hardware_concurrency"]}}});
        Object.defineProperty(navigator, 'deviceMemory', {{get: () => {fp["device_memory"]}}});
        if (!window.chrome) {{
            window.chrome = {{runtime: {{}}, app: {{}}, csi: () => {{}}, loadTimes: () => {{}}}};
        }}
        const getParameterProto = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{fp["webgl_vendor"]}';
            if (parameter === 37446) return '{fp["webgl_renderer"]}';
            return getParameterProto.call(this, parameter);
        }};
    }} catch (e) {{}}
}})();"""

def human_delay(min_s: float = 2.0, max_s: float = 6.0):
    mean = (min_s + max_s) / 2
    delay = random.expovariate(1.0 / mean) if mean > 0 else min_s
    time.sleep(max(min_s, min(delay, max_s)))

def jitter_sleep(base_s: float, jitter_s: float = 0.6):
    time.sleep(max(0.1, base_s + random.uniform(0, jitter_s)))

def random_batch_size(base: int = 40, lo: int = 25, hi: int = 55) -> int:
    return max(5, random.randint(lo, hi))

def random_session_offset(max_s: int = 180):
    time.sleep(random.uniform(0, max_s))

def _today() -> str: return time.strftime("%Y-%m-%d")

def load_daily_state(cookie_file: str) -> dict:
    os.makedirs(STATE_DIR, exist_ok=True)
    state_path = os.path.join(STATE_DIR, "daily_state.json")
    states = _safe_read_json(state_path)
    key = os.path.basename(cookie_file)
    today = _today()

    if key not in states or states[key].get("date") != today:
        states[key] = {
            "date": today, "claims_today": 0, "transfers_today": 0,
            "amount_transferred": 0, "sessions_today": 0,
            "last_run_ts": 0, "soft_ban_until": 0,
        }
        _safe_write_json(state_path, states)
    return states[key]

def save_daily_state(cookie_file: str, state: dict):
    state_path = os.path.join(STATE_DIR, "daily_state.json")
    states = _safe_read_json(state_path)
    states[os.path.basename(cookie_file)] = state
    _safe_write_json(state_path, states)

def check_daily_quota(cookie_file: str) -> tuple:
    st = load_daily_state(cookie_file)
    if st["claims_today"] >= DEFAULT_MAX_CLAIMS_PER_DAY: return False, f"đã claim đủ quota ngày"
    if st["transfers_today"] >= DEFAULT_MAX_TRANSFERS_PER_DAY: return False, f"đã transfer đủ quota ngày"
    if st.get("soft_ban_until", 0) > time.time(): return False, f"đang bị soft-ban"
    return True, "ok"

def record_claim(cookie_file: str, amount: int = 0):
    st = load_daily_state(cookie_file)
    st["claims_today"] = st.get("claims_today", 0) + 1
    save_daily_state(cookie_file, st)

def record_transfer(cookie_file: str, amount: int = 0):
    st = load_daily_state(cookie_file)
    st["transfers_today"] = st.get("transfers_today", 0) + 1
    st["amount_transferred"] = st.get("amount_transferred", 0) + amount
    save_daily_state(cookie_file, st)

def record_session_start(cookie_file: str):
    st = load_daily_state(cookie_file)
    st["sessions_today"] = st.get("sessions_today", 0) + 1
    st["last_run_ts"] = int(time.time())
    save_daily_state(cookie_file, st)

def set_soft_ban(cookie_file: str, duration_s: int = 900):
    st = load_daily_state(cookie_file)
    st["soft_ban_until"] = int(time.time()) + duration_s
    save_daily_state(cookie_file, st)

def detect_soft_ban(text: str) -> bool:
    if not text: return False
    t = str(text).lower()
    return any(h in t for h in ("rate limit", "too many requests", "spam", "tạm thời", "khóa tạm", "restricted"))

def stealth_launch_args() -> list:
    return [
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-notifications", "--disable-extensions", "--disable-gpu-sandbox"
    ]

def maybe_idle_browse(page, max_claims_so_far: int, every: int = 60):
    if max_claims_so_far <= 0 or max_claims_so_far % every != 0: return
    wait = random.uniform(30, 90)
    print(f"  😴 Đã claim {max_claims_so_far} lần — nghỉ {wait:.0f}s giả lập người dùng.", flush=True)
    try: page.mouse.wheel(0, random.randint(100, 400))
    except Exception: pass
    time.sleep(wait)

def warm_up_account(page):
    try:
        page.mouse.wheel(0, random.randint(200, 600))
        time.sleep(random.uniform(2, 4))
    except Exception: pass


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
# GAME SESSION & FRAME RECOVERY CORE
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
            return bool(f.evaluate("() => typeof window !== 'undefined'"))
        except Exception: return False

    def _click_fb_play_button(self):
        try:
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
        except Exception: pass

    def _scan_frames(self):
        try: frames = list(self.page.frames)
        except Exception: return None
        for f in frames:
            try:
                if not f.is_detached() and ("instant-bundle" in (f.url or "").lower() or "fbsbx.com" in (f.url or "").lower()):
                    if self._frame_alive(f): return f
            except Exception: continue
        for f in frames:
            try:
                if not f.is_detached() and f.evaluate("() => typeof window !== 'undefined' && !!(window.connection || document.querySelector('.chipBalance') || typeof window.createTable === 'function')"):
                    return f
            except Exception: continue
        return None

    def find_frame(self, max_wait=FRAME_WAIT, verbose=True):
        deadline = time.time() + max_wait
        last_click_try = 0
        while time.time() < deadline:
            if self.page.is_closed(): raise SessionDead("Page đã bị đóng")
            if time.time() - last_click_try > 5:
                self._click_fb_play_button()
                last_click_try = time.time()
            f = self._scan_frames()
            if f:
                self.gf = f
                if verbose: log("  ✓ Tìm thấy game frame")
                return f
            time.sleep(2)
        if verbose: log(f"  ⚠ Không thấy game frame sau {max_wait}s")
        return None

    def frame(self, quick=True):
        if self._frame_alive(self.gf): return self.gf
        self.gf = None
        return self.find_frame(max_wait=8 if quick else FRAME_WAIT, verbose=False)

    def eval(self, js, arg=None, default=None, retries=1):
        for attempt in range(retries + 1):
            if self.page.is_closed(): raise SessionDead("Page đã bị đóng")
            f = self.frame()
            if not f:
                if attempt < retries: time.sleep(2); continue
                return default
            try: return f.evaluate(js, arg)
            except Exception as e:
                if is_frame_error(str(e)): self.gf = None
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
            if not self._frame_alive(self.gf): self.gf = None
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
        if self.recover_fail >= MAX_RECOVER_FAIL: raise SessionDead(f"Recover thất bại {self.recover_fail} lần")

        since = time.time() - self.last_reload_ts
        if self.last_reload_ts and since < RELOAD_COOLDOWN:
            w = RELOAD_COOLDOWN - since
            if w > self.time_left() - MIN_TIME_LEFT: raise SessionDead("Không đủ thời gian cooldown")
            time.sleep(w)

        self.reloads += 1
        self.last_reload_ts = time.time()
        hard = (self.reloads % 2 == 0)
        log(f"  🔄 RECOVER #{self.reloads}/{MAX_RELOADS_PER_SESSION} ({'goto' if hard else 'reload'}) — {reason}")

        self.gf = None
        try:
            if hard: self.page.goto(GAME_URL, wait_until="domcontentloaded", timeout=60000)
            else: self.page.reload(wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
        except Exception as e:
            if "closed" in str(e).lower(): raise SessionDead("Page closed khi navigate")
            self.recover_fail += 1
            if self.recover_fail >= MAX_RECOVER_FAIL: raise SessionDead("Navigate liên tục thất bại")
            return False

        self.check_page_health()
        if not self.find_frame(max_wait=FRAME_WAIT, verbose=True):
            self.recover_fail += 1
            if self.recover_fail >= MAX_RECOVER_FAIL: raise SessionDead("Không tìm được game frame")
            return False

        if not self.wait_ws(WS_WAIT):
            self.recover_fail += 1
            if self.recover_fail >= MAX_RECOVER_FAIL: raise SessionDead("WS không kết nối")
            return False

        self.recover_fail = 0
        log("  ✅ RECOVER OK — Frame + WS đã sẵn sàng")
        return True

    def ensure_ready(self, reason="check", attempts=2):
        if self.frame() and self.ws_ok(): return True
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
# JS PAYLOADS & ACTIONS
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

def transfer_all_xu(s: GameSession, dest_id=TRANSFER_DEST_ID):
    if not s.ensure_ready("transfer"): return {"success": False, "error": "Session chưa sẵn sàng"}
    res = s.eval(JS_TRANSFER, dest_id, default=None, retries=1)
    return res if res else {"success": False, "error": "evaluate failed"}

def trigger_and_claim(s: GameSession):
    if not s.ensure_ready("claim"): return {"success": False, "error": "Session chưa sẵn sàng"}
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
        if attempt == 0:
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
# RUN SESSION & MAIN
# ============================================================
def run_session(p, fb_cookies, session_id, started_at):
    log(f"\n########## SESSION {session_id} ##########")
    browser = context = page = None
    total_reward = total_transferred = ok = fail_total = 0
    cookie_ok = True

    try:
        fp = get_or_create_fingerprint(SINGLE_COOKIE_FILE)
        browser = p.chromium.launch(headless=HEADLESS, args=stealth_launch_args())
        context = browser.new_context(viewport=fp["viewport"], locale=fp["locale"], user_agent=fp["user_agent"], timezone_id=fp["timezone"])

        try: context.add_init_script(build_stealth_js(fp))
        except Exception: pass

        context.add_cookies([dict(c, domain=".facebook.com") for c in fb_cookies])
        page = context.new_page()
        page.set_default_timeout(45000)
        s = GameSession(page, started_at)

        log("[1] Login FB...")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
        s.check_page_health()

        if WARMUP_ENABLED: warm_up_account(page)

        log("[2] Open game...")
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=60000)
        if not s.find_frame(max_wait=FRAME_WAIT):
            s.recover("Frame không xuất hiện ban đầu")

        log("[3] Wait WS...")
        if not s.wait_ws(WS_WAIT) and not s.ensure_ready("WS khởi động"):
            return 0, 0, 0, 0, True

        if s.is_account_blocked():
            log("  ❌ ACCOUNT BLOCKED — dừng")
            return 0, 0, 0, 0, False

        log(f"  Balance Start: {s.get_bal()}")

        ok_quota, reason = check_daily_quota(SINGLE_COOKIE_FILE)
        if not ok_quota:
            log(f"  ⏸ [ANTI-BAN] Bỏ qua: {reason}")
            return 0, 0, 0, 0, True
        record_session_start(SINGLE_COOKIE_FILE)

        claim_count = batch_no = consec_fail = 0
        dest_id = TRANSFER_DEST_ID

        log(f"\n[4] BATCH MODE: ~{CLAIM_BATCH} -> transfer")
        while True:
            if s.time_left() <= MIN_TIME_LEFT: break
            batch_no += 1
            cur_batch = random_batch_size(CLAIM_BATCH)

            bal_num = parse_balance_num(s.get_bal())
            if TRANSFER_ENABLED and bal_num > PRE_CLAIM_TRANSFER_THRESHOLD:
                r = transfer_all_xu(s, dest_id)
                if r.get("success"):
                    amt = r.get("balance", 0)
                    total_transferred += amt
                    log(f"  ✅ Chuyển trước batch {amt:,} -> {dest_id}")
                    if detect_soft_ban(r.get("message", "")) or detect_soft_ban(r.get("error", "")):
                        set_soft_ban(SINGLE_COOKIE_FILE)
                        return total_reward, total_transferred, ok, fail_total, True
                    record_transfer(SINGLE_COOKIE_FILE, amt)
                    time.sleep(2)

            log(f"\n[Batch #{batch_no}] {cur_batch} claims...")
            stop_session = False
            for i in range(cur_batch):
                if s.time_left() <= MIN_TIME_LEFT: stop_session = True; break
                s.close_dialogs()
                jitter_sleep(1.0, 1.0)

                result = trigger_and_claim(s)
                if detect_soft_ban(result.get("error", "")) or detect_soft_ban(result.get("message", "")):
                    set_soft_ban(SINGLE_COOKIE_FILE)
                    return total_reward, total_transferred, ok, fail_total, True

                if result.get("success") and result.get("amount", 0) > 0:
                    amount = result["amount"]
                    total_reward += amount; ok += 1; claim_count += 1; consec_fail = 0
                    record_claim(SINGLE_COOKIE_FILE, amount)
                    jitter_sleep(1.0, 0.8)
                    log(f"    ✅ OK +{amount} | Tổng: {total_reward:,}")
                    if IDLE_EVERY_CLAIMS > 0: maybe_idle_browse(page, claim_count, every=IDLE_EVERY_CLAIMS)
                else:
                    fail_total += 1; consec_fail += 1
                    if parse_balance_num(s.get_bal()) >= 50000: break
                    if consec_fail >= MAX_CONSEC_CLAIM_FAIL:
                        if not s.ensure_ready("Nhiều claim fail", attempts=1): stop_session = True; break
                        consec_fail = 0

                human_delay(max(2.0, DELAY), max(4.0, DELAY+3.0))

            if TRANSFER_ENABLED and parse_balance_num(s.get_bal()) > 200:
                r = transfer_all_xu(s, dest_id)
                if r.get("success"):
                    amt = r.get("balance", 0)
                    total_transferred += amt
                    log(f"  ✅ Chuyển sau batch {amt:,} -> {dest_id}")
                    if detect_soft_ban(r.get("message", "")) or detect_soft_ban(r.get("error", "")):
                        set_soft_ban(SINGLE_COOKIE_FILE)
                        return total_reward, total_transferred, ok, fail_total, True
                    record_transfer(SINGLE_COOKIE_FILE, amt)

            if stop_session: break
            human_delay(max(3.0, DELAY), max(8.0, DELAY+5.0))

    except SessionDead as e:
        log(f"\n[SESSION {session_id}] 💀 DEAD: {e}")
        if "cookie chết" in str(e) or "logout" in str(e) or "checkpoint" in str(e): cookie_ok = False
    except Exception as e: log(f"\n[SESSION {session_id}] ⚠ Lỗi: {type(e).__name__}: {str(e)[:160]}")
    finally:
        if page:
            try: page.close()
            except: pass
        if context:
            try: context.close()
            except: pass
        if browser:
            try: browser.close(); log("  🧹 Dọn dẹp Browser an toàn")
            except: pass

    return total_reward, total_transferred, ok, fail_total, cookie_ok

def main():
    log("=" * 64)
    log("FB Tien Len Mien Nam — SINGLE FILE BOT v13")
    log("=" * 64)
    cookies = load_single_cookie_set(SINGLE_COOKIE_FILE)
    if not cookies: return 1
    fb_cookies = parse_cookie(cookies[0]["raw"])
    if not fb_cookies: log("[STOP] Cookie parse lỗi."); return 1

    ok_q, reason = check_daily_quota(SINGLE_COOKIE_FILE)
    if not ok_q: log(f"\n[ANTI-BAN] ⏸ Dừng: {reason}"); return 0
    if SESSION_START_JITTER > 0: random_session_offset(SESSION_START_JITTER)

    started_at = time.time()
    session_id, grand_reward, grand_transfer, grand_ok, grand_fail = 0, 0, 0, 0, 0

    with sync_playwright() as p:
        while session_id < MAX_SESSIONS:
            if (MAX_RUNTIME - (time.time() - started_at)) <= MIN_TIME_LEFT: break
            session_id += 1
            rw, tr, ok, fail, cookie_ok = run_session(p, fb_cookies, session_id, started_at)
            grand_reward += rw; grand_transfer += tr; grand_ok += ok; grand_fail += fail
            if not cookie_ok: break
            if session_id < MAX_SESSIONS:
                time.sleep(min(REST, max(5, int(MAX_RUNTIME - (time.time() - started_at) - MIN_TIME_LEFT))))

    log(f"\n{'=' * 64}\nTỔNG KẾT: {session_id} ss | {grand_ok} OK | {grand_fail} fail | rw={grand_reward:,} | tr={grand_transfer:,}\n{'=' * 64}")
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt: sys.exit(130)

```
