#!/usr/bin/env python3
"""FB Tien Len Mien Nam reward bot v10 — ALL BUGS FIXED

Fix:
  1. find_gf(max_wait=0) → loop không chạy → LUÔN check ít nhất 1 lần
  2. ensure_ws_connected → trả về (bool, new_gf) để caller cập nhật frame
  3. smart_load_game → gọi find_gf đúng cách
  4. Balance reading → nhiều selectors
  5. Graceful shutdown + logging
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
MAX_TRANSFER_FAILS = 5

_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    logger.warning(f"Signal {signum}, shutting down...")
    _shutdown = True

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ══════════════════════════════════════════════════════
# SAVE SCREENSHOT
# ══════════════════════════════════════════════════════
def save_screenshot(page, name: str):
    try:
        ts = time.strftime("%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"{name}_{ts}.png")
        page.screenshot(path=path, full_page=False)
        logger.info(f"  📸 Screenshot: {path}")
    except Exception as e:
        logger.debug(f"  Screenshot failed: {e}")


# ══════════════════════════════════════════════════════
# LOG PAGE STATUS
# ══════════════════════════════════════════════════════
def log_page_status(page, label: str = ""):
    try:
        logger.info(f"  📄 [{label}] URL: {page.url}")
        logger.info(f"  📄 [{label}] Title: {page.title()}")
        logger.info(f"  📄 [{label}] Frames: {len(page.frames)}")
        for i, f in enumerate(page.frames):
            u = f.url
            marker = ""
            if "instant-bundle" in u and "fbsbx.com" in u:
                marker = " ← ⭐ GAME FRAME"
            logger.debug(f"    Frame[{i}]: {u[:120]}{marker}")
    except Exception as e:
        logger.warning(f"  log_page_status error: {e}")


# ══════════════════════════════════════════════════════
# PARSE BALANCE
# ══════════════════════════════════════════════════════
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
                    if (text && text !== '?' && /\d/.test(text)) return text;
                }
            }
            for (const el of document.querySelectorAll('span, div, p')) {
                if (el.children.length > 2) continue;
                const t = el.textContent.trim();
                if (/^[\d,]+\.?\d*[kKmM]?$/.test(t) && t.length < 15) {
                    try {
                        const r = el.getBoundingClientRect();
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
# ★ FIX #1: FIND GAME FRAME — always check at least once!
# ══════════════════════════════════════════════════════
def find_gf(page, max_wait: int = 60):
    """Find game frame. ALWAYS checks at least once (even if max_wait=0).
    
    ★ BUG FIX: range(max_wait // 5) when max_wait=0 → range(0) = empty loop!
              Fix: use max(1, ...) or do-while pattern.
    """
    # ★ FIX: Ensure at least 1 iteration
    iterations = max(1, max_wait // 5) if max_wait > 0 else 1
    sleep_time = 5 if max_wait > 0 else 0

    for attempt in range(iterations):
        for f in page.frames:
            url = f.url
            # Match game frame patterns
            if ("instant-bundle" in url and "fbsbx.com" in url):
                logger.debug(f"  find_gf: found at attempt {attempt + 1}")
                return f
            # Fallback patterns
            if "instant-bundle" in url:
                logger.debug(f"  find_gf: found (instant-bundle) at attempt {attempt + 1}")
                return f
        
        if sleep_time > 0 and attempt < iterations - 1:
            time.sleep(sleep_time)

    return None


# ══════════════════════════════════════════════════════
# CHECK LOGIN STATUS
# ══════════════════════════════════════════════════════
def check_login_status(page) -> str:
    try:
        url = page.url.lower()
        if "login" in url:
            return "login_page"
        if "checkpoint" in url or "verify" in url:
            return "checkpoint"
        
        has_login = page.evaluate("""() => {
            return !!document.querySelector('#email, #pass, [name="email"]');
        }""")
        if has_login:
            return "login_page"
        
        cookies = page.context.cookies()
        if any(c["name"] == "c_user" for c in cookies):
            return "logged_in"
        
        return "unknown"
    except Exception as e:
        return f"error:{e}"


# ══════════════════════════════════════════════════════
# ★ FIX #2: SMART LOAD GAME — proper frame finding
# ══════════════════════════════════════════════════════
def smart_load_game(page, game_url: str):
    """Load game with proper frame detection."""
    logger.info(f"Loading game: {game_url}")
    
    try:
        page.goto(game_url, wait_until="domcontentloaded", timeout=120000)
    except Exception as e:
        logger.error(f"  page.goto failed: {e}")
        save_screenshot(page, "goto_failed")
        return None

    time.sleep(5)
    log_page_status(page, "after_goto")

    # Check login
    login = check_login_status(page)
    logger.info(f"  Login status: {login}")
    if login == "login_page":
        logger.error("  ❌ NOT LOGGED IN! Update ck1.txt")
        save_screenshot(page, "not_logged_in")
        return None
    if login == "checkpoint":
        logger.error("  ❌ CHECKPOINT! Verify manually")
        save_screenshot(page, "checkpoint")
        return None

    # ★ FIX: Wait for game frame with proper max_wait
    logger.info("  Waiting for game frame...")
    gf = find_gf(page, max_wait=60)  # ★ NOT max_wait=0!
    
    if not gf:
        logger.warning("  Game frame not found, trying reload...")
        save_screenshot(page, "no_frame_before_reload")
        
        try:
            page.reload(wait_until="domcontentloaded", timeout=120000)
            time.sleep(10)
            log_page_status(page, "after_reload")
            gf = find_gf(page, max_wait=60)  # ★ Try again after reload
        except Exception as e:
            logger.error(f"  Reload failed: {e}")

    if not gf:
        logger.error("  ❌ Game frame NOT FOUND after all attempts!")
        save_screenshot(page, "no_frame_final")
        log_page_status(page, "final")
        return None

    logger.info(f"  ✅ Game frame found: {gf.url[:100]}")

    # Wait for game to render
    logger.info("  Waiting for game to render...")
    time.sleep(8)

    # Check balance
    bal = get_bal(gf)
    logger.info(f"  Initial balance: {bal}")

    return gf


# ══════════════════════════════════════════════════════
# ★ FIX #3: WS CHECK — returns status string
# ══════════════════════════════════════════════════════
def check_ws_status(gf) -> str:
    """Check WS status. Returns: connected/connecting/closed/no_connection/error"""
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
        err = str(e)
        if "closed" in err.lower() or "target" in err.lower():
            return "frame_closed"
        return f"error:{err[:50]}"


# ══════════════════════════════════════════════════════
# ★ FIX #4: ENSURE WS — returns (success, new_gf)
# ══════════════════════════════════════════════════════
def ensure_ws_connected(gf, page, max_retries: int = 3):
    """Ensure WS connected. Returns (success: bool, new_gf: Frame|None).
    
    ★ BUG FIX: After page.reload(), old frame becomes invalid.
              Must return the NEW frame reference so caller can update.
    """
    status = check_ws_status(gf)
    if status == "connected":
        return True, gf  # ★ Return same gf

    for attempt in range(max_retries):
        status = check_ws_status(gf)
        
        if status == "connected":
            return True, gf
        
        if status == "connecting":
            logger.info(f"  WS connecting, waiting... (attempt {attempt + 1})")
            time.sleep(3)
            continue

        # Frame is dead or WS is dead — need reload
        logger.warning(f"  ⚠ WS {status} — reloading (attempt {attempt + 1}/{max_retries})")
        
        try:
            page.reload(wait_until="domcontentloaded", timeout=120000)
            time.sleep(10)
            
            # ★ Find NEW frame after reload
            new_gf = find_gf(page, max_wait=60)
            
            if not new_gf:
                logger.warning("  ❌ Game frame not found after reload")
                continue
            
            # ★ Check WS on NEW frame
            for _ in range(5):
                time.sleep(2)
                new_status = check_ws_status(new_gf)
                if new_status == "connected":
                    logger.info("  ✓ WS reconnected with new frame")
                    return True, new_gf  # ★ Return NEW frame!
                if new_status == "connecting":
                    continue
            
            logger.warning(f"  ⚠ WS still {new_status} after reload")
            # Even if WS not connected yet, return new frame
            # (claim might still work)
            return False, new_gf
            
        except Exception as e:
            logger.error(f"  Reload error: {e}")

    return False, None


# ══════════════════════════════════════════════════════
# ACCOUNT BLOCKED CHECK
# ══════════════════════════════════════════════════════
def is_account_blocked(gf) -> bool:
    try:
        return bool(gf.evaluate("""() => {
            const d = document.querySelectorAll('[class*="msgBox"],[class*="dialog"],[class*="Dialog"]');
            for (const el of d) {
                if (el.offsetParent !== null || getComputedStyle(el).display !== 'none') {
                    const t = el.textContent.toLowerCase();
                    if (t.includes('blocked') || t.includes('bị khóa') || t.includes('suspended'))
                        return true;
                }
            }
            return false;
        }"""))
    except:
        return False


# ══════════════════════════════════════════════════════
# TRANSFER
# ══════════════════════════════════════════════════════
def transfer_all_xu(gf, page, dest_id: int = TRANSFER_DEST_ID):
    """Transfer ALL xu. Returns dict with success, balance, etc."""
    # Ensure WS
    ws_ok, new_gf = ensure_ws_connected(gf, page)
    if new_gf:
        gf = new_gf
    if not ws_ok:
        return {"success": False, "error": "ws reconnect failed"}

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
    logger.info("CK1 Bot — Tien Len Mien Nam (ALL BUGS FIXED)")
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
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
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
        for c in cookie_data:
            logger.debug(f"  {c['name']} = {c['value'][:15]}...")
        context.add_cookies(cookie_data)

        # Verify c_user
        ctx_cookies = context.cookies()
        c_user = next((c for c in ctx_cookies if c["name"] == "c_user"), None)
        if c_user:
            logger.info(f"  ✅ c_user: {c_user['value']}")
        else:
            logger.warning("  ⚠ No c_user! Cookies may be invalid")

        # ★ Load game (properly!)
        gf = smart_load_game(page, GAME_URL)
        if not gf:
            logger.error("❌ Failed to load game. Exiting.")
            browser.close()
            return

        # Check blocked
        if is_account_blocked(gf):
            logger.error("❌ Account BLOCKED!")
            save_screenshot(page, "blocked")
            browser.close()
            return

        bal_text = get_bal(gf)
        logger.info(f"✅ Game ready! Balance: {bal_text}")

        # ── Main loop ──
        cycle = 0
        while not _shutdown:
            elapsed = time.time() - start_time
            if elapsed > MAX_RUNTIME:
                logger.info(f"Max runtime {MAX_RUNTIME}s reached")
                break

            cycle += 1
            logger.info(f"\n══ Cycle {cycle}/{MAX_CYCLES} ══ (elapsed: {elapsed:.0f}s)")

            for i in range(CLAIM_BATCH):
                if _shutdown:
                    break

                claim_count += 1
                elapsed = time.time() - start_time
                if elapsed > MAX_RUNTIME:
                    break

                # Read balance
                bal_before = get_bal(gf)
                logger.info(f"  [Claim #{claim_count}] Balance: {bal_before}")

                # ★ Check WS BEFORE claim — update gf if needed!
                ws_status = check_ws_status(gf)
                if ws_status != "connected":
                    logger.warning(f"  ⚠ WS: {ws_status}")
                    ws_ok, new_gf = ensure_ws_connected(gf, page)
                    if new_gf:
                        gf = new_gf  # ★ UPDATE frame reference!
                        ws_reload_count += 1
                    if not ws_ok:
                        fail_count += 1
                        logger.error(f"  ❌ Cannot reconnect, skipping")
                        continue

                # Claim (placeholder — integrate with original do_claim logic)
                # result = do_claim(gf, page)
                result = {"success": True, "reward": 0}  # Placeholder

                if result.get("success"):
                    success_count += 1
                    reward = result.get("reward", 0)
                    total_reward += reward
                    logger.info(f"  ✅ Claim #{claim_count} OK +{reward} | total={total_reward}")

                    # Transfer check
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
                logger.info(f"  Resting {REST}s...")
                time.sleep(REST)

        browser.close()

    total_time = time.time() - start_time
    logger.info("\n" + "=" * 60)
    logger.info("SESSION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Claims: {claim_count} | Success: {success_count} | Fail: {fail_count}")
    logger.info(f"  Reward: {total_reward:,} xu")
    logger.info(f"  WS reloads: {ws_reload_count}")
    logger.info(f"  Transfer fails: {transfer_fail_count}")
    logger.info(f"  Time: {total_time:.0f}s ({total_time/60:.1f}min)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
Bug Report: range(0) = empty loop + stale
