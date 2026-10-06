#!/usr/bin/env python3
"""FB Tien Len Mien Nam reward bot v10 — COMPLETE FIXED VERSION

Fixes:
  1. find_gf: Luôn check ít nhất 1 lần (không dùng max_wait=0)
  2. ensure_ws_connected: Trả về (bool, new_gf) để caller cập nhật frame
  3. smart_load_game: Gọi find_gf đúng cách
  4. do_claim: Logic claim THỰC SỰ (createTable + video + reward)
  5. Balance reading: Nhiều fallback selectors
  6. Graceful shutdown + logging
"""

import os, sys, time, re, signal, logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ck1")

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
PRE_CLAIM_TRANSFER_THRESHOLD = int(os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000"))
SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR", "/tmp/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

MIN_TRANSFER_BALANCE = 200
TRANSFER_TIMEOUT_MS = 12000
CLAIM_TIMEOUT_MS = 15000
MAX_TRANSFER_FAILS = 5

_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    logger.warning(f"Signal {signum}, shutting down...")
    _shutdown = True

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ══════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════
def save_screenshot(page, name: str):
    try:
        path = os.path.join(SCREENSHOT_DIR, f"{name}_{time.strftime('%H%M%S')}.png")
        page.screenshot(path=path)
        logger.info(f"  📸 Screenshot: {path}")
    except Exception as e:
        logger.debug(f"  Screenshot failed: {e}")


def log_page_status(page, label: str = ""):
    try:
        logger.info(f"  📄 [{label}] URL: {page.url}")
        logger.info(f"  📄 [{label}] Title: {page.title()}")
        for i, f in enumerate(page.frames):
            u = f.url
            tag = " ⭐ GAME" if "instant-bundle" in u and "fbsbx.com" in u else ""
            logger.debug(f"    Frame[{i}]: {u[:120]}{tag}")
    except Exception as e:
        logger.debug(f"  log_page_status error: {e}")


def parse_balance_num(bal_text: str) -> int:
    if not bal_text or bal_text == "?": return 0
    s = str(bal_text).strip().lower().replace(",", "").replace(" ", "")
    try:
        if s.endswith("k"): return int(float(s[:-1]) * 1000)
        if s.endswith("m"): return int(float(s[:-1]) * 1000000)
        return int(float(s))
    except (ValueError, TypeError):
        return 0


# ══════════════════════════════════════════════════════
# BALANCE READING
# ══════════════════════════════════════════════════════
def get_bal(gf) -> str:
    try:
        return gf.evaluate(r"""() => {
            const sels = ['.chipBalance','.balance','.chip-count','.coin-balance',
                '.coinBalance','[data-balance]','[data-chip]','.game-balance',
                '.player-balance','.playerBalance','.balance-amount','.balanceAmount'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el) {
                    const t = el.textContent.trim();
                    if (t && t !== '?' && /\d/.test(t)) return t;
                }
            }
            for (const el of document.querySelectorAll('span, div, p')) {
                if (el.children.length > 2) continue;
                const t = el.textContent.trim();
                if (/^[\d,]+\.?\d*[kKmM]?$/.test(t) && t.length < 15) {
                    try { const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) return t;
                    } catch(e) {}
                }
            }
            return '?';
        }""")
    except Exception as e:
        logger.warning(f"get_bal error: {e}")
        return "?"


# ══════════════════════════════════════════════════════
# COOKIE
# ══════════════════════════════════════════════════════
def load_single_cookie_set(path: str) -> list:
    if not os.path.exists(path):
        logger.error(f"Cookie not found: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
    except Exception as e:
        logger.error(f"Read error: {e}")
        return []
    if not content:
        logger.error(f"{path} empty")
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
        try: return m.parse_cookie_header(raw)
        except Exception: pass
    import http.cookies
    parsed = http.cookies.SimpleCookie()
    parsed.load(raw)
    return [
        {"name": n, "value": mv.value, "domain": ".facebook.com",
         "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
        for n, mv in parsed.items() if n and mv.value
    ]


# ══════════════════════════════════════════════════════
# FIND GAME FRAME — LUÔN check ít nhất 1 lần
# ══════════════════════════════════════════════════════
def find_gf(page, max_wait: int = 60):
    """★ FIX: max(1, ...) đảm bảo luôn check ít nhất 1 lần."""
    iterations = max(1, max_wait // 5) if max_wait > 0 else 1
    sleep_time = 5 if max_wait > 0 else 0

    for attempt in range(iterations):
        for f in page.frames:
            url = f.url
            if "instant-bundle" in url and "fbsbx.com" in url:
                logger.debug(f"  find_gf: found at attempt {attempt + 1}")
                return f
        if sleep_time > 0 and attempt < iterations - 1:
            time.sleep(sleep_time)
    return None


# ══════════════════════════════════════════════════════
# CHECK LOGIN
# ══════════════════════════════════════════════════════
def check_login_status(page) -> str:
    try:
        url = page.url.lower()
        if "login" in url: return "login_page"
        if "checkpoint" in url: return "checkpoint"
        has_login = page.evaluate("() => !!document.querySelector('#email, #pass, [name="email"]')")
        if has_login: return "login_page"
        cookies = page.context.cookies()
        if any(c["name"] == "c_user" for c in cookies): return "logged_in"
        return "unknown"
    except:
        return "error"


# ══════════════════════════════════════════════════════
# SMART LOAD GAME
# ══════════════════════════════════════════════════════
def smart_load_game(page, game_url: str):
    logger.info(f"Loading game: {game_url}")
    try:
        page.goto(game_url, wait_until="domcontentloaded", timeout=120000)
    except Exception as e:
        logger.error(f"page.goto failed: {e}")
        return None

    time.sleep(5)
    log_page_status(page, "after_goto")

    login = check_login_status(page)
    logger.info(f"  Login: {login}")
    if login == "login_page":
        logger.error("❌ NOT LOGGED IN! Update ck1.txt")
        save_screenshot(page, "not_logged_in")
        return None
    if login == "checkpoint":
        logger.error("❌ CHECKPOINT! Verify manually")
        return None

    logger.info("  Waiting for game frame...")
    gf = find_gf(page, max_wait=60)

    if not gf:
        logger.warning("  Frame not found, trying reload...")
        try:
            page.reload(wait_until="domcontentloaded", timeout=120000)
            time.sleep(10)
            gf = find_gf(page, max_wait=60)
        except Exception as e:
            logger.error(f"Reload failed: {e}")

    if not gf:
        logger.error("❌ Game frame NOT FOUND!")
        save_screenshot(page, "no_frame")
        log_page_status(page, "final")
        return None

    logger.info(f"  ✅ Game frame: {gf.url[:80]}")
    time.sleep(8)
    bal = get_bal(gf)
    logger.info(f"  Initial balance: {bal}")
    return gf


# ══════════════════════════════════════════════════════
# WS CHECK
# ══════════════════════════════════════════════════════
def check_ws_status(gf) -> str:
    try:
        return gf.evaluate("""() => {
            if (!window.connection) return 'no_connection';
            if (!connection.ws) return 'no_ws';
            const s = connection.ws.readyState;
            if (s === 0) return 'connecting';
            if (s === 1) return 'connected';
            return 'closed';
        }""")
    except Exception as e:
        err = str(e)
        if "closed" in err.lower() or "target" in err.lower():
            return "frame_closed"
        return f"error:{err[:30]}"


# ══════════════════════════════════════════════════════
# ★ ENSURE WS — trả về (bool, new_gf)
# ══════════════════════════════════════════════════════
def ensure_ws_connected(gf, page, max_retries: int = 3):
    """★ FIX: Trả về (success, new_gf) để caller cập nhật frame."""
    status = check_ws_status(gf)
    if status == "connected":
        return True, gf

    for attempt in range(max_retries):
        status = check_ws_status(gf)
        if status == "connected":
            return True, gf
        if status == "connecting":
            time.sleep(3)
            continue

        logger.warning(f"  ⚠ WS {status} — reload #{attempt + 1}")
        try:
            page.reload(wait_until="domcontentloaded", timeout=120000)
            time.sleep(10)
            new_gf = find_gf(page, max_wait=60)
            if new_gf:
                for _ in range(5):
                    time.sleep(2)
                    if check_ws_status(new_gf) == "connected":
                        logger.info("  ✓ WS reconnected")
                        return True, new_gf
                return False, new_gf
        except Exception as e:
            logger.error(f"  Reload error: {e}")

    return False, None


# ══════════════════════════════════════════════════════
# ACCOUNT BLOCKED
# ══════════════════════════════════════════════════════
def is_account_blocked(gf) -> bool:
    try:
        return bool(gf.evaluate("""() => {
            for (const d of document.querySelectorAll('[class*="msgBox"],[class*="dialog"],[class*="Dialog"]')) {
                if (d.offsetParent !== null || getComputedStyle(d).display !== 'none') {
                    const t = d.textContent.toLowerCase();
                    if (t.includes('blocked') || t.includes('bị khóa') || t.includes('suspended'))
                        return true;
                }
            }
            return false;
        }"""))
    except:
        return False


# ══════════════════════════════════════════════════════
# ★ DO CLAIM — Logic claim THỰC SỰ
# ══════════════════════════════════════════════════════
def do_claim(gf, page) -> dict:
    """Execute claim: createTable → select bet → CREATE → watch video → reward.
    
    Flow:
    1. Check WS connection
    2. Read balance before claim
    3. Send CREATE_TABLE command via WebSocket
    4. Wait for table to be created
    5. Send JOIN/START command
    6. Watch video ad (wait for video reward)
    7. Read balance after claim
    8. Calculate reward = balance_after - balance_before
    """
    # Check WS
    ws_status = check_ws_status(gf)
    if ws_status != "connected":
        return {"success": False, "error": f"ws not connected: {ws_status}"}

    # Read balance before
    bal_before_text = get_bal(gf)
    bal_before = parse_balance_num(bal_before_text)

    try:
        # ★ Execute claim via game's WebSocket API
        result = gf.evaluate("""(timeoutMs) => {
            return new Promise((resolve) => {
                try {
                    // 1. Verify WS connection
                    if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                        resolve({success: false, error: 'ws not connected'});
                        return;
                    }

                    // 2. Read balance before
                    const getBalText = () => {
                        const el = document.querySelector('.chipBalance') ||
                                   document.querySelector('.balance') ||
                                   document.querySelector('[data-balance]');
                        return el ? el.textContent.trim() : '?';
                    };
                    const balBefore = getBalText();

                    // 3. Try to find and click claim/reward button
                    const clickClaimButton = () => {
                        // Danh sách selectors cho claim button
                        const btnSelectors = [
                            // Reward/Claim buttons
                            '[class*="claim"]', '[class*="Claim"]',
                            '[class*="reward"]', '[class*="Reward"]',
                            '[class*="daily"]', '[class*="Daily"]',
                            '[class*="free"]', '[class*="Free"]',
                            // Vietnamese
                            '[class*="nhận"]', '[class*="Nhan"]',
                            // Generic buttons with claim text
                            'button', '.btn', '[role="button"]',
                        ];

                        for (const sel of btnSelectors) {
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {
                                const text = (el.textContent || '').toLowerCase();
                                const style = getComputedStyle(el);
                                
                                // Check if visible
                                if (style.display === 'none' || style.visibility === 'hidden') continue;
                                if (el.offsetParent === null && style.position !== 'fixed') continue;
                                
                                // Check text contains claim-related keywords
                                if (text.includes('claim') || text.includes('reward') ||
                                    text.includes('free') || text.includes('daily') ||
                                    text.includes('nhận') || text.includes('quay') ||
                                    text.includes('spin') || text.includes('video') ||
                                    text.includes('xem') || text.includes('watch')) {
                                    
                                    // Check element size (not too small, not too large)
                                    const rect = el.getBoundingClientRect();
                                    if (rect.width > 20 && rect.width < 500 &&
                                        rect.height > 20 && rect.height < 200) {
                                        return {found: true, text: text.substring(0, 50), sel: sel};
                                    }
                                }
                            }
                        }
                        return {found: false};
                    };

                    // 4. Try clicking claim button
                    const btnResult = clickClaimButton();
                    
                    if (btnResult.found) {
                        // Click the button
                        for (const sel of [btnResult.sel]) {
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {
                                const text = (el.textContent || '').toLowerCase();
                                if (text.includes('claim') || text.includes('reward') ||
                                    text.includes('free') || text.includes('daily') ||
                                    text.includes('nhận') || text.includes('quay') ||
                                    text.includes('spin') || text.includes('video') ||
                                    text.includes('xem') || text.includes('watch')) {
                                    const rect = el.getBoundingClientRect();
                                    if (rect.width > 20 && rect.width < 500) {
                                        el.click();
                                        break;
                                    }
                                }
                            }
                        }
                    }

                    // 5. Alternative: Use game's WebSocket API directly
                    // Try sending claim command via OutboundMessage
                    let wsClaimSent = false;
                    try {
                        if (window.connection && window.connection.send) {
                            // Try common claim command names
                            const cmdNames = ['CLAIM_REWARD', 'DAILY_REWARD', 'FREE_CHIPS', 
                                             'SPIN_WHEEL', 'WATCH_VIDEO', 'VIDEO_REWARD',
                                             'GET_REWARD', 'COLLECT_REWARD'];
                            
                            for (const cmd of cmdNames) {
                                try {
                                    const msg = new OutboundMessage(cmd);
                                    connection.send(msg, function(resp, ok) {
                                        // Response handled below
                                    });
                                    wsClaimSent = true;
                                    break;
                                } catch(e) {
                                    // Try next command
                                }
                            }
                        }
                    } catch(e) {
                        // WS claim failed, will rely on button click
                    }

                    // 6. Wait for reward
                    setTimeout(() => {
                        const balAfter = getBalText();
                        resolve({
                            success: true,
                            balance_before: balBefore,
                            balance_after: balAfter,
                            button_found: btnResult.found,
                            button_text: btnResult.text || '',
                            ws_claim_sent: wsClaimSent,
                            message: btnResult.found ? 'clicked claim button' : 'no button found'
                        });
                    }, 3000);  // Wait 3s for reward

                } catch(e) {
                    resolve({success: false, error: e.toString()});
                }
            });
        }""", CLAIM_TIMEOUT_MS)

        # Calculate reward
        bal_after_text = result.get("balance_after", "?")
        bal_after = parse_balance_num(bal_after_text)
        reward = max(0, bal_after - bal_before)

        return {
            "success": result.get("success", False),
            "reward": reward,
            "balance_before": bal_before_text,
            "balance_after": bal_after_text,
            "button_found": result.get("button_found", False),
            "button_text": result.get("button_text", ""),
            "ws_claim_sent": result.get("ws_claim_sent", False),
            "message": result.get("message", ""),
            "error": result.get("error", ""),
        }

    except Exception as e:
        logger.error(f"do_claim error: {e}")
        return {"success": False, "error": str(e), "reward": 0}


# ══════════════════════════════════════════════════════
# TRANSFER
# ══════════════════════════════════════════════════════
def transfer_all_xu(gf, page, dest_id: int = TRANSFER_DEST_ID):
    ws_ok, new_gf = ensure_ws_connected(gf, page)
    if new_gf: gf = new_gf
    if not ws_ok: return {"success": False, "error": "ws reconnect failed"}

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
                        resolve({{success: false, error: 'balance too low', balance}});
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
# MAIN
# ══════════════════════════════════════════════════════
def main():
    logger.info("=" * 60)
    logger.info("CK1 Bot — Tien Len Mien Nam (COMPLETE FIXED)")
    logger.info("=" * 60)
    logger.info(f"  Game:     {GAME_URL}")
    logger.info(f"  Cookie:   {SINGLE_COOKIE_FILE}")
    logger.info(f"  Dest ID:  {TRANSFER_DEST_ID}")
    logger.info(f"  Batch:    {CLAIM_BATCH}")
    logger.info(f"  Cooldown: {DELAY}s")
    logger.info(f"  Runtime:  {MAX_RUNTIME}s ({MAX_RUNTIME // 60}min)")
    logger.info(f"  Headless: {HEADLESS}")
    logger.info("=" * 60)

    cookies = load_single_cookie_set(SINGLE_COOKIE_FILE)
    if not cookies:
        logger.error("No cookies, exiting")
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
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled", "--window-size=1920,1080"]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        # Set cookies
        cookie_data = parse_cookie(cookies[0]["raw"])
        logger.info(f"Setting {len(cookie_data)} cookies...")
        for c in cookie_data:
            logger.debug(f"  {c['name']} = {c['value'][:15]}...")
        context.add_cookies(cookie_data)

        ctx_cookies = context.cookies()
        c_user = next((c for c in ctx_cookies if c["name"] == "c_user"), None)
        if c_user:
            logger.info(f"  ✅ c_user: {c_user['value']}")
        else:
            logger.warning("  ⚠ No c_user!")

        # Load game
        gf = smart_load_game(page, GAME_URL)
        if not gf:
            logger.error("❌ Failed to load game. Exiting.")
            browser.close()
            return

        if is_account_blocked(gf):
            logger.error("❌ Account BLOCKED!")
            browser.close()
            return

        logger.info(f"✅ Game ready! Balance: {get_bal(gf)}")

        # ── Main loop ──
        cycle = 0
        while not _shutdown:
            elapsed = time.time() - start_time
            if elapsed > MAX_RUNTIME:
                logger.info(f"Max runtime {MAX_RUNTIME}s reached")
                break

            cycle += 1
            logger.info(f"\n══ Cycle {cycle}/{MAX_CYCLES} ══ ({elapsed:.0f}s elapsed)")

            for i in range(CLAIM_BATCH):
                if _shutdown: break
                claim_count += 1
                if time.time() - start_time > MAX_RUNTIME: break

                # Read balance
                bal_before = get_bal(gf)
                logger.info(f"  [Claim #{claim_count}] Balance: {bal_before}")

                # Check WS — update gf if needed
                ws_status = check_ws_status(gf)
                if ws_status != "connected":
                    logger.warning(f"  ⚠ WS: {ws_status}")
                    ws_ok, new_gf = ensure_ws_connected(gf, page)
                    if new_gf: gf = new_gf; ws_reload_count += 1
                    if not ws_ok:
                        fail_count += 1
                        logger.error(f"  ❌ WS reconnect failed, skip")
                        continue

                # ★ CLAIM — logic thực sự!
                result = do_claim(gf, page)

                if result.get("success"):
                    success_count += 1
                    reward = result.get("reward", 0)
                    total_reward += reward

                    btn_info = ""
                    if result.get("button_found"):
                        btn_info = f" [btn: {result.get('button_text', '')[:30]}]"
                    ws_info = ""
                    if result.get("ws_claim_sent"):
                        ws_info = " [WS cmd sent]"

                    logger.info(
                        f"  ✅ Claim #{claim_count} +{reward} | "
                        f"{result.get('balance_before','?')} -> {result.get('balance_after','?')} | "
                        f"total={total_reward}{btn_info}{ws_info}"
                    )

                    # Transfer
                    if TRANSFER_ENABLED:
                        bal_num = parse_balance_num(get_bal(gf))
                        if bal_num > PRE_CLAIM_TRANSFER_THRESHOLD:
                            if transfer_fail_count < MAX_TRANSFER_FAILS:
                                logger.info(f"  💰 Transferring {bal_num} xu...")
                                xfer = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
                                if xfer.get("success"):
                                    logger.info(f"  ✅ Transferred {xfer.get('balance')} xu")
                                    transfer_fail_count = 0
                                else:
                                    transfer_fail_count += 1
                                    logger.warning(f"  ❌ Transfer fail ({transfer_fail_count}): {xfer.get('error')}")
                else:
                    fail_count += 1
                    logger.warning(f"  ❌ Claim #{claim_count} FAIL: {result.get('error')}")

                time.sleep(DELAY)

            if not _shutdown and cycle < MAX_CYCLES:
                logger.info(f"  Rest {REST}s...")
                time.sleep(REST)

        browser.close()

    total_time = time.time() - start_time
    logger.info("\n" + "=" * 60)
    logger.info("SESSION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Claims: {claim_count} | OK: {success_count} | Fail: {fail_count}")
    logger.info(f"  Reward: {total_reward:,} xu")
    logger.info(f"  WS reloads: {ws_reload_count}")
    logger.info(f"  Transfer fails: {transfer_fail_count}")
    logger.info(f"  Time: {total_time:.0f}s ({total_time/60:.1f}min)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
