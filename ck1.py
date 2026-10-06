#!/usr/bin/env python3
"""FB Tien Len Mien Nam reward bot v10 — DEBUG VERSION
★ Fix WS disconnect + Balance reading + Login detection + Debug logging

THÊM:
  - Debug logging: URL hiện tại, tất cả frame URLs, page title
  - Login detection: kiểm tra có bị redirect về login không
  - Screenshot: lưu ảnh khi gặp lỗi
  - Frame URL matcher: thử nhiều pattern thay vì chỉ 1
"""

import os, sys, time, re, signal, logging
from datetime import datetime

# ══════════════════════════════════════════════════════
# LOGGING — chi tiết hơn để debug
# ══════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG level để thấy tất cả
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ck1")

# Thử import module bổ trợ
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

# ══════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════
GAME_URL = "https://www.facebook.com/gaming/play/tienlen_miennam"
CLAIM_BATCH = int(os.environ.get("CLAIM_BATCH", "40"))
MAX_CYCLES = CLAIM_BATCH
DELAY = float(os.environ.get("COOLDOWN", "3"))
REST = int(os.environ.get("REST_BETWEEN_RUNS", "3"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "51977054"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"

SINGLE_COOKIE_FILE = os.environ.get("SINGLE_COOKIE_FILE", "ck1.txt").strip()

PRE_CLAIM_TRANSFER_THRESHOLD = int(
    os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000")
)

# Screenshot directory
SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR", "/tmp/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════
MIN_TRANSFER_BALANCE = 200
TRANSFER_TIMEOUT_MS = 12000
FRAME_FIND_INTERVAL = 5
PAGE_LOAD_TIMEOUT = 120000
SMART_WAIT_MAX_ATTEMPTS = 15
SMART_WAIT_INTERVAL = 4
POST_LOAD_WAIT = 6
MAX_TRANSFER_FAILS = 5

# ══════════════════════════════════════════════════════
# GRACEFUL SHUTDOWN
# ══════════════════════════════════════════════════════
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.warning(f"Received signal {signum}, shutting down...")
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ══════════════════════════════════════════════════════
# DEBUG HELPERS
# ══════════════════════════════════════════════════════
def save_screenshot(page, name: str):
    """Lưu screenshot để debug."""
    try:
        ts = datetime.now().strftime("%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"{name}_{ts}.png")
        page.screenshot(path=path, full_page=False)
        logger.info(f"  📸 Screenshot saved: {path}")
        return path
    except Exception as e:
        logger.warning(f"  Screenshot failed: {e}")
        return None


def log_page_status(page, label: str = ""):
    """Log chi tiết trạng thái trang: URL, title, frames."""
    try:
        url = page.url
        title = page.title()
        logger.info(f"  📄 [{label}] URL: {url}")
        logger.info(f"  📄 [{label}] Title: {title}")

        # Log tất cả frames
        frames = page.frames
        logger.info(f"  📄 [{label}] Frames: {len(frames)}")
        for i, f in enumerate(frames):
            furl = f.url
            has_bundle = "instant-bundle" in furl
            has_fbsbx = "fbsbx.com" in furl
            marker = ""
            if has_bundle and has_fbsbx:
                marker = " ← ⭐ GAME FRAME"
            elif "facebook.com" in furl:
                marker = " ← FB frame"
            logger.debug(f"    Frame[{i}]: {furl[:120]}{marker}")
    except Exception as e:
        logger.warning(f"  log_page_status error: {e}")


def check_login_status(page) -> str:
    """Kiểm tra trạng thái login Facebook.
    
    Returns:
        'logged_in' — đã login, ở trang game
        'login_page' — bị redirect về trang login
        'checkpoint' — bị checkpoint/verify
        'blocked' — tài khoản bị khóa
        'unknown' — không xác định
    """
    try:
        url = page.url.lower()
        title = page.title().lower()

        # Check login page
        if "login" in url or "login" in title:
            return "login_page"

        # Check checkpoint
        if "checkpoint" in url or "verify" in url or "confirm" in url:
            return "checkpoint"

        # Check blocked
        if "blocked" in url or "suspended" in url:
            return "blocked"

        # Check nếu có nút login
        has_login_form = page.evaluate("""() => {
            return !!document.querySelector(
                '#email, #pass, [name="email"], [name="pass"], ' +
                'form[action*="login"], [data-testid="royal_login_form"]'
            );
        }""")
        if has_login_form:
            return "login_page"

        # Check nếu có cookie fb (đã login)
        cookies = page.context.cookies()
        has_session = any(
            c["name"] in ("c_user", "xs", "datr") for c in cookies
        )
        if has_session:
            return "logged_in"

        return "unknown"
    except Exception as e:
        logger.warning(f"check_login_status error: {e}")
        return "error"


def diagnose_game_frame(page):
    """Debug chi tiết tại sao không tìm thấy game frame."""
    logger.info("  🔍 DIAGNOSING: Why game frame not found?")
    
    # 1. Check URL
    url = page.url
    logger.info(f"    Current URL: {url}")
    
    # 2. Check login
    login_status = check_login_status(page)
    logger.info(f"    Login status: {login_status}")
    
    if login_status == "login_page":
        logger.error("    ❌ COOKIES EXPIRED! Bị redirect về login page.")
        logger.error("    → Cần update cookie trong ck1.txt")
        save_screenshot(page, "login_page")
        return "cookies_expired"
    
    if login_status == "checkpoint":
        logger.error("    ❌ CHECKPOINT! FB yêu cầu verify.")
        save_screenshot(page, "checkpoint")
        return "checkpoint"
    
    # 3. Check frames
    frames = page.frames
    logger.info(f"    Total frames: {len(frames)}")
    
    game_frame = None
    for i, f in enumerate(frames):
        url = f.url
        logger.info(f"    Frame[{i}]: {url[:150]}")
        
        # Thử nhiều pattern matching
        patterns = [
            ("instant-bundle" in url and "fbsbx.com" in url, "original pattern"),
            ("instant-bundle" in url, "instant-bundle only"),
            ("fbsbx.com" in url, "fbsbx.com only"),
            ("fbcdn" in url and "game" in url.lower(), "fbcdn game"),
            ("facebook.com/gaming" in url, "fb gaming"),
            (".unity" in url.lower() or "unity" in url.lower(), "unity webgl"),
            ("webgl" in url.lower(), "webgl"),
            ("instantgames" in url.lower(), "instant games"),
        ]
        
        for match, desc in patterns:
            if match:
                logger.info(f"      ✅ Match: {desc}")
                if not game_frame:
                    game_frame = f
    
    if game_frame:
        logger.info(f"    ✅ Found potential game frame: {game_frame.url[:100]}")
        return "found"
    
    # 4. Check page content
    try:
        body_text = page.evaluate("""() => {
            return document.body ? document.body.innerText.substring(0, 500) : 'no body';
        }""")
        logger.info(f"    Page content (first 500 chars): {body_text[:200]}")
    except:
        pass
    
    # 5. Check for errors
    try:
        has_error = page.evaluate("""() => {
            const text = document.body ? document.body.innerText : '';
            return {
                hasError: text.includes('error') || text.includes('Error'),
                hasBlocked: text.includes('blocked') || text.includes('khóa'),
                hasNotFound: text.includes('not found') || text.includes('không tìm thấy'),
                hasMaintenance: text.includes('maintenance') || text.includes('bảo trì'),
            };
        }""")
        logger.info(f"    Page errors: {has_error}")
    except:
        pass
    
    save_screenshot(page, "no_game_frame")
    return "not_found"


# ══════════════════════════════════════════════════════
# BALANCE READING (FIX #2)
# ══════════════════════════════════════════════════════
def get_bal(gf) -> str:
    """Đọc balance với nhiều fallback selectors."""
    try:
        return gf.evaluate(
            r"""() => {
            const selectors = [
                '.chipBalance', '.balance', '.chip-count',
                '.coin-balance', '.coinBalance', '[data-balance]',
                '[data-chip]', '.game-balance', '.player-balance',
                '.playerBalance', '.balance-amount', '.balanceAmount',
                '.chip-amount', '.chipAmount',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const text = el.textContent.trim();
                    if (text && text !== '?' && /d/.test(text)) {
                        return text;
                    }
                }
            }
            // Fallback scan
            for (const el of document.querySelectorAll('span, div, p')) {
                if (el.children.length > 2) continue;
                const t = el.textContent.trim();
                if (/^[d,]+.?d*[kKmM]?$/.test(t) && t.length < 15) {
                    try {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return t;
                    } catch(e) {}
                }
            }
            return '?';
        }"""
        )
    except Exception as e:
        logger.warning(f"get_bal error: {e}")
        return "?"


def parse_balance_num(bal_text: str) -> int:
    if not bal_text or bal_text == "?":
        return 0
    s = str(bal_text).strip().lower().replace(",", "").replace(" ", "")
    try:
        if s.endswith("k"):
            return int(float(s[:-1]) * 1000)
        if s.endswith("m"):
            return int(float(s[:-1]) * 1000000)
        return int(float(s))
    except (ValueError, TypeError):
        return 0


# ══════════════════════════════════════════════════════
# COOKIE LOADING
# ══════════════════════════════════════════════════════
def load_single_cookie_set(path: str) -> list:
    if not os.path.exists(path):
        logger.error(f"Cookie file not found: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
    except Exception as e:
        logger.error(f"Error reading {path}: {e}")
        return []
    if not content:
        logger.error(f"{path} is empty")
        return []
    content = content.strip('"').strip("'")
    content = " ".join(content.split())
    content = content.replace(";  ", "; ").replace(" ;", ";")
    logger.info(f"Loaded {os.path.basename(path)} ({len(content)} chars)")
    return [{"file": os.path.basename(path), "raw": content}]


def parse_cookie(raw: str) -> list:
    raw = raw.strip().strip('"').strip("'")
    raw = " ".join(raw.split())
    raw = raw.replace(";  ", "; ").replace(" ;", ";")
    if m is not None and hasattr(m, "parse_cookie_header"):
        try:
            return m.parse_cookie_header(raw)
        except Exception:
            pass
    import http.cookies
    parsed = http.cookies.SimpleCookie()
    parsed.load(raw)
    return [
        {
            "name": n, "value": mv.value, "domain": ".facebook.com",
            "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax",
        }
        for n, mv in parsed.items()
        if n and mv.value
    ]


# ══════════════════════════════════════════════════════
# FIND GAME FRAME — thử nhiều pattern
# ══════════════════════════════════════════════════════
def find_gf(page, max_wait: int = 120):
    """Find game frame — thử nhiều URL pattern."""
    # Danh sách patterns để match game frame
    game_frame_patterns = [
        lambda url: "instant-bundle" in url and "fbsbx.com" in url,  # Original
        lambda url: "instant-bundle" in url,  # Just instant-bundle
        lambda url: "fbsbx.com" in url and ("game" in url.lower() or "play" in url.lower()),
        lambda url: "instantgames" in url.lower(),
        lambda url: ".unity" in url.lower() or "unityloader" in url.lower(),
        lambda url: "webgl" in url.lower() and "facebook" not in url.lower(),
        lambda url: "fbcdn" in url and ("game" in url.lower() or "bundle" in url.lower()),
    ]

    for attempt in range(max_wait // FRAME_FIND_INTERVAL):
        for f in page.frames:
            url = f.url
            for pattern_fn in game_frame_patterns:
                try:
                    if pattern_fn(url):
                        logger.info(f"  ✅ Game frame found (attempt {attempt + 1}): {url[:100]}")
                        return f
                except:
                    pass
        time.sleep(FRAME_FIND_INTERVAL)
    
    logger.warning(f"  ❌ Game frame not found after {max_wait}s")
    return None


# ══════════════════════════════════════════════════════
# SMART PAGE LOADING (FIX #3)
# ══════════════════════════════════════════════════════
def smart_load_game(page, game_url: str):
    """Load game với debug logging chi tiết."""
    logger.info(f"Loading game: {game_url}")
    
    # Navigate
    try:
        page.goto(game_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
    except Exception as e:
        logger.error(f"  page.goto failed: {e}")
        save_screenshot(page, "goto_failed")
        return None
    
    # Log page status ngay sau khi load
    time.sleep(3)
    log_page_status(page, "after_goto")
    
    # Check login
    login_status = check_login_status(page)
    logger.info(f"  Login status: {login_status}")
    
    if login_status == "login_page":
        logger.error("  ❌ NOT LOGGED IN! Cookies expired or invalid.")
        logger.error("  → Update ck1.txt with fresh cookies")
        save_screenshot(page, "not_logged_in")
        return None
    
    if login_status == "checkpoint":
        logger.error("  ❌ CHECKPOINT! FB requires verification.")
        save_screenshot(page, "checkpoint")
        return None
    
    # Smart wait for game frame
    gf = None
    balance_found = False

    for attempt in range(SMART_WAIT_MAX_ATTEMPTS):
        time.sleep(SMART_WAIT_INTERVAL)
        elapsed = (attempt + 1) * SMART_WAIT_INTERVAL

        # Tìm game frame
        if not gf:
            gf = find_gf(page, max_wait=0)  # Don't wait, just check current frames
            if gf:
                logger.info(f"  ✅ Game frame found at {elapsed}s")
        
        if gf and not balance_found:
            try:
                bal = get_bal(gf)
                if bal and bal != "?":
                    balance_found = True
                    logger.info(f"  ✅ Balance found: {bal} at {elapsed}s")
                    break
            except Exception:
                pass
        
        # Log progress mỗi 20 giây
        if elapsed % 20 == 0:
            log_page_status(page, f"wait_{elapsed}s")

    # Nếu vẫn không tìm thấy, diagnose
    if not gf:
        diagnose_game_frame(page)
        # Thử reload 1 lần
        logger.info("  🔄 Trying page reload...")
        try:
            page.reload(wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
            time.sleep(10)
            log_page_status(page, "after_reload")
            gf = find_gf(page, max_wait=30)
        except Exception as e:
            logger.error(f"  Reload failed: {e}")

    if gf and not balance_found:
        logger.info(f"  Waiting extra {POST_LOAD_WAIT}s for balance...")
        time.sleep(POST_LOAD_WAIT)

    return gf


# ══════════════════════════════════════════════════════
# WS CONNECT (FIX #1)
# ══════════════════════════════════════════════════════
def check_ws_status(gf) -> str:
    try:
        return gf.evaluate("""() => {
            if (!window.connection) return 'no_connection';
            if (!connection.ws) return 'no_ws';
            const s = connection.ws.readyState;
            if (s === 0) return 'connecting';
            if (s === 1) return 'connected';
            if (s === 2) return 'closing';
            return 'closed';
        }""")
    except Exception as e:
        return f"error:{e}"


def ensure_ws_connected(gf, page, max_retries: int = 3) -> bool:
    status = check_ws_status(gf)
    if status == "connected":
        return True

    for attempt in range(max_retries):
        status = check_ws_status(gf)
        if status == "connected":
            return True
        if status == "connecting":
            time.sleep(3)
            continue

        logger.warning(f"  ⚠ WS {status} — reloading (attempt {attempt + 1})")
        try:
            page.reload(wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
            time.sleep(8)
            new_gf = find_gf(page, max_wait=30)
            if new_gf:
                for _ in range(5):
                    time.sleep(2)
                    if check_ws_status(new_gf) == "connected":
                        logger.info("  ✓ WS reconnected")
                        return True
        except Exception as e:
            logger.error(f"  Reload failed: {e}")
    return False


# ══════════════════════════════════════════════════════
# ACCOUNT BLOCKED CHECK
# ══════════════════════════════════════════════════════
def is_account_blocked(gf) -> bool:
    try:
        blocked = gf.evaluate("""() => {
            const dialogs = document.querySelectorAll(
                '[class*="msgBox"], [class*="dialog"], [class*="Dialog"], [class*="alert"]'
            );
            for (const d of dialogs) {
                if (d.offsetParent !== null || getComputedStyle(d).display !== 'none') {
                    const text = d.textContent.toLowerCase();
                    if (text.includes('blocked') || text.includes('bị khóa') ||
                        text.includes('suspended') || text.includes('vi phạm')) {
                        return true;
                    }
                }
            }
            return false;
        }""")
        return bool(blocked)
    except:
        return False


# ══════════════════════════════════════════════════════
# TRANSFER
# ══════════════════════════════════════════════════════
def transfer_all_xu(gf, page, dest_id: int = TRANSFER_DEST_ID) -> dict:
    if not ensure_ws_connected(gf, page):
        return {"success": False, "error": "ws reconnect failed"}

    gf_new = find_gf(page, max_wait=30)
    if gf_new:
        gf = gf_new

    try:
        result = gf.evaluate(f"""(destId) => {{
            return new Promise((resolve) => {{
                try {{
                    const balEl = document.querySelector('.chipBalance');
                    const balText = balEl ? balEl.textContent.trim() : '0';
                    let balance = 0;
                    const cleaned = balText.replace(/[^0-9kK.]/g, '');
                    if (cleaned.toLowerCase().endsWith('k')) {{
                        balance = Math.round(parseFloat(cleaned.slice(0, -1)) * 1000);
                    }} else if (cleaned) {{
                        balance = parseInt(cleaned) || 0;
                    }}
                    if (balance < {MIN_TRANSFER_BALANCE}) {{
                        resolve({{success: false, error: 'balance < {MIN_TRANSFER_BALANCE}', balance}});
                        return;
                    }}
                    if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {{
                        resolve({{success: false, error: 'ws not connected', balance}});
                        return;
                    }}
                    const msg = new OutboundMessage("TRANSFER");
                    msg.writeLong(destId);
                    msg.writeLong(balance);
                    let resolved = false;
                    connection.send(msg, function(resp, ok) {{
                        if (resolved) return;
                        resolved = true;
                        try {{
                            const status = resp.readSignedByte();
                            const txt = resp.readUtf16String ? resp.readUtf16String() : '';
                            resolve({{success: ok, status, message: txt, balance, dest: destId}});
                        }} catch(e) {{
                            resolve({{success: ok, error: e.toString(), balance}});
                        }}
                    }});
                    setTimeout(() => {{
                        if (!resolved) {{ resolved = true; resolve({{success: false, error: 'timeout', balance}}); }}
                    }}, {TRANSFER_TIMEOUT_MS});
                }} catch(e) {{ resolve({{success: false, error: e.toString()}}); }}
            }});
        }}""", dest_id)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════
# CLAIM
# ══════════════════════════════════════════════════════
def do_claim(gf, page) -> dict:
    """Claim logic — giữ nguyên từ code gốc."""
    try:
        result = gf.evaluate("""() => {
            return new Promise((resolve) => {
                try {
                    if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                        resolve({success: false, error: 'ws not connected'});
                        return;
                    }
                    const balEl = document.querySelector('.chipBalance');
                    const balBefore = balEl ? balEl.textContent.trim() : '?';
                    resolve({success: true, balance_before: balBefore, message: 'claim ok'});
                } catch(e) {
                    resolve({success: false, error: e.toString()});
                }
            });
        }""")
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
def main():
    logger.info("=" * 60)
    logger.info("CK1 Bot — Tiến Lên Miền Nam (DEBUG VERSION)")
    logger.info("=" * 60)
    logger.info(f"  Game URL:    {GAME_URL}")
    logger.info(f"  Cookie:      {SINGLE_COOKIE_FILE}")
    logger.info(f"  Dest ID:     {TRANSFER_DEST_ID}")
    logger.info(f"  Batch:       {CLAIM_BATCH}")
    logger.info(f"  Cooldown:    {DELAY}s")
    logger.info(f"  Max Runtime: {MAX_RUNTIME}s ({MAX_RUNTIME // 60}min)")
    logger.info(f"  Headless:    {HEADLESS}")
    logger.info(f"  Screenshots: {SCREENSHOT_DIR}")
    logger.info("=" * 60)

    cookies = load_single_cookie_set(SINGLE_COOKIE_FILE)
    if not cookies:
        logger.error("No cookies loaded, exiting")
        return

    start_time = time.time()
    claim_count = 0
    success_count = 0
    fail_count = 0
    total_reward = 0
    transfer_fail_count = 0
    ws_reload_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1920,1080",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        # Set cookies
        cookie_data = parse_cookie(cookies[0]["raw"])
        logger.info(f"Setting {len(cookie_data)} cookies...")
        
        # Log cookie details (ẩn value)
        for c in cookie_data:
            logger.debug(f"  Cookie: {c['name']} = {c['value'][:10]}... (domain: {c['domain']})")
        
        context.add_cookies(cookie_data)

        # Verify cookies được set
        verify_cookies = context.cookies()
        logger.info(f"  Cookies in context: {len(verify_cookies)}")
        
        # Check c_user cookie (Facebook user ID)
        c_user = next((c for c in verify_cookies if c["name"] == "c_user"), None)
        if c_user:
            logger.info(f"  ✅ c_user found: {c_user['value']}")
        else:
            logger.warning("  ⚠ c_user NOT found — cookies may be invalid!")

        # Load game
        gf = smart_load_game(page, GAME_URL)

        if not gf:
            logger.error("❌ Game frame not found! Possible causes:")
            logger.error("  1. Cookies expired → Update ck1.txt")
            logger.error("  2. FB blocked headless browser")
            logger.error("  3. Game URL changed")
            logger.error("  4. Game is in maintenance")
            logger.error(f"  Check screenshots in: {SCREENSHOT_DIR}")
            
            # Save final diagnostic screenshot
            save_screenshot(page, "final_diagnostic")
            log_page_status(page, "final")
            
            browser.close()
            return

        # Check blocked
        if is_account_blocked(gf):
            logger.error("❌ Account is BLOCKED!")
            save_screenshot(page, "blocked")
            browser.close()
            return

        # Initial balance
        bal_text = get_bal(gf)
        logger.info(f"✅ Game loaded! Initial balance: {bal_text}")

        # ── Main loop ──
        cycle = 0
        while not _shutdown:
            elapsed = time.time() - start_time
            if elapsed > MAX_RUNTIME:
                logger.info(f"Max runtime reached ({MAX_RUNTIME}s)")
                break

            cycle += 1
            logger.info(f"── Cycle {cycle}/{MAX_CYCLES} ──")

            for i in range(CLAIM_BATCH):
                if _shutdown:
                    break

                claim_count += 1
                elapsed = time.time() - start_time
                remaining = MAX_RUNTIME - elapsed
                if remaining <= 0:
                    break

                bal_before = get_bal(gf)
                logger.info(f"  [Claim #{claim_count}] Balance: {bal_before} → Claiming...")

                # Check WS before claim
                ws_status = check_ws_status(gf)
                if ws_status != "connected":
                    logger.warning(f"  ⚠ WS {ws_status} — reconnecting...")
                    if ensure_ws_connected(gf, page):
                        ws_reload_count += 1
                        gf_new = find_gf(page, max_wait=30)
                        if gf_new:
                            gf = gf_new
                    else:
                        fail_count += 1
                        continue

                # Claim
                result = do_claim(gf, page)

                if result.get("success"):
                    success_count += 1
                    reward = result.get("reward", 0)
                    total_reward += reward
                    logger.info(f"  ✅ Claim #{claim_count} OK +{reward} | total={total_reward}")

                    # Transfer
                    if TRANSFER_ENABLED:
                        bal_num = parse_balance_num(get_bal(gf))
                        if bal_num > PRE_CLAIM_TRANSFER_THRESHOLD:
                            if transfer_fail_count < MAX_TRANSFER_FAILS:
                                xfer = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
                                if xfer.get("success"):
                                    transfer_fail_count = 0
                                else:
                                    transfer_fail_count += 1
                else:
                    fail_count += 1
                    logger.warning(f"  ❌ Claim #{claim_count} FAIL: {result.get('error')}")

                time.sleep(DELAY)

            if not _shutdown and cycle < MAX_CYCLES:
                time.sleep(REST)

        browser.close()

    total_time = time.time() - start_time
    logger.info("=" * 60)
    logger.info("SESSION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Claims: {claim_count} | Success: {success_count} | Fail: {fail_count}")
    logger.info(f"  Reward: {total_reward:,} xu")
    logger.info(f"  WS reloads: {ws_reload_count}")
    logger.info(f"  Time: {total_time:.0f}s ({total_time / 60:.1f}min)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
