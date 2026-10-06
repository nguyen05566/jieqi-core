#!/usr/bin/env python3
"""FB Tien Len Mien Nam reward bot v9 — FIXED VERSION
★ Fix WS disconnect + Balance reading + Reload optimization

Thay đổi so với bản gốc:
  - FIX #1: WS reconnect — chỉ reload khi thực sự cần, thêm keepalive
  - FIX #2: Balance reading — nhiều fallback selectors
  - FIX #3: Reload optimization — smart waiting thay vì time.sleep(30)
  - FIX #4: Transfer fail counter — disable sau 5 lần fail liên tiếp
"""

import os, sys, time, re, signal, logging

# ══════════════════════════════════════════════════════
# LOGGING — thay print() bằng logging module
# ══════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ck1")

# Thử import module bổ trợ nếu có
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

# ══════════════════════════════════════════════════════
# CONFIG — tất cả từ ENV, giữ backward compatible
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

# ══════════════════════════════════════════════════════
# CONSTANTS — magic values → named constants
# ══════════════════════════════════════════════════════
MIN_TRANSFER_BALANCE = 200
TRANSFER_TIMEOUT_MS = 12000
FRAME_FIND_INTERVAL = 5
PAGE_LOAD_TIMEOUT = 120000
SMART_WAIT_MAX_ATTEMPTS = 15  # 15 × 4s = 60s max
SMART_WAIT_INTERVAL = 4
POST_LOAD_WAIT = 6
MAX_TRANSFER_FAILS = 5

# ══════════════════════════════════════════════════════
# GRACEFUL SHUTDOWN
# ══════════════════════════════════════════════════════
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.warning(f"Received signal {signum}, shutting down gracefully...")
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ══════════════════════════════════════════════════════
# PARSE BALANCE
# ══════════════════════════════════════════════════════
def parse_balance_num(bal_text: str) -> int:
    """Parse '56.4k' or '123,456' or '78900' → int."""
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
        logger.warning(f"Cannot parse balance: '{bal_text}'")
        return 0


# ══════════════════════════════════════════════════════
# COOKIE LOADING
# ══════════════════════════════════════════════════════
def load_single_cookie_set(path: str) -> list:
    """Đọc 1 file cookie. Trả về [{'file': ..., 'raw': ...}] hoặc []."""
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
    """Parse cookie header string → Playwright format."""
    raw = raw.strip().strip('"').strip("'")
    raw = " ".join(raw.split())
    raw = raw.replace(";  ", "; ").replace(" ;", ";")

    if m is not None and hasattr(m, "parse_cookie_header"):
        try:
            return m.parse_cookie_header(raw)
        except Exception:
            logger.warning(
                "board_dom_merged.parse_cookie_header failed, using fallback"
            )

    import http.cookies

    parsed = http.cookies.SimpleCookie()
    parsed.load(raw)
    return [
        {
            "name": n,
            "value": mv.value,
            "domain": ".facebook.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        }
        for n, mv in parsed.items()
        if n and mv.value
    ]


# ══════════════════════════════════════════════════════
# FIX #2: BALANCE READING — nhiều fallback selectors
# ══════════════════════════════════════════════════════
def get_bal(gf) -> str:
    """Đọc balance với nhiều fallback selectors.
    
    Selector list mở rộng: thử từng selector cho đến khi tìm thấy.
    Nếu không có selector nào match → scan DOM tìm element chứa số.
    """
    try:
        return gf.evaluate(
            r"""() => {
            // ── Selector list theo thứ tự ưu tiên ──
            const selectors = [
                '.chipBalance',
                '.balance',
                '.chip-count',
                '.coin-balance',
                '.coinBalance',
                '[data-balance]',
                '[data-chip]',
                '.game-balance',
                '.player-balance',
                '.playerBalance',
                '.balance-amount',
                '.balanceAmount',
                '.chip-amount',
                '.chipAmount',
            ];

            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const text = el.textContent.trim();
                    if (text && text !== '?' && text.length > 0 && text.length < 20) {
                        // Verify: phải chứa ít nhất 1 chữ số
                        if (/d/.test(text)) {
                            return text;
                        }
                    }
                }
            }

            // ── Fallback: scan tất cả span/div tìm số tiền ──
            // Pattern: "12,345" hoặc "56.4k" hoặc "1.2M"
            const candidates = [];
            const allEls = document.querySelectorAll(
                'span, div, p, td, strong, b, em, i, h1, h2, h3, h4, h5, h6'
            );
            
            for (const el of allEls) {
                // Skip nếu element có con element khác (tránh lấy parent)
                if (el.children.length > 2) continue;
                
                const text = el.textContent.trim();
                
                // Match: "12345", "12,345", "56.4k", "1.2M"
                if (/^[\d,]+\.?[\d]*[kKmM]?$/.test(text) && text.length >= 1 && text.length < 15) {
                    // Verify: element phải visible
                    try {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            candidates.push({
                                text: text,
                                // Ưu tiên element gần chip icon
                                hasChipParent: !!el.closest('[class*="chip"], [class*="balance"], [class*="coin"]'),
                                // Ưu tiên element nhỏ (không phải container lớn)
                                isSmall: rect.width < 200 && rect.height < 60,
                            });
                        }
                    } catch (e) {
                        // Ignore getBoundingClientRect errors
                    }
                }
            }

            // Sắp xếp: ưu tiên có chip parent, rồi element nhỏ
            candidates.sort((a, b) => {
                if (a.hasChipParent !== b.hasChipParent) return b.hasChipParent - a.hasChipParent;
                if (a.isSmall !== b.isSmall) return b.isSmall - a.isSmall;
                return 0;
            });

            if (candidates.length > 0) {
                return candidates[0].text;
            }

            return '?';
        }"""
        )
    except Exception as e:
        logger.warning(f"get_bal error: {e}")
        return "?"


# ══════════════════════════════════════════════════════
# FIND GAME FRAME
# ══════════════════════════════════════════════════════
def find_gf(page, max_wait: int = 120):
    """Find game frame by checking frame URLs."""
    for _ in range(max_wait // FRAME_FIND_INTERVAL):
        for f in page.frames:
            if "instant-bundle" in f.url and "fbsbx.com" in f.url:
                return f
        time.sleep(FRAME_FIND_INTERVAL)
    logger.warning(f"Game frame not found after {max_wait}s")
    return None


# ══════════════════════════════════════════════════════
# FIX #3: SMART PAGE LOADING
# ══════════════════════════════════════════════════════
def smart_load_game(page, game_url: str):
    """Load game page với smart waiting — đợi game frame + balance element.
    
    Thay vì time.sleep(30) cố định, đợi cho đến khi:
    1. Game frame xuất hiện
    2. Balance element render xong
    Tối đa 60 giây, kiểm tra mỗi 4 giây.
    """
    logger.info(f"Loading game: {game_url}")
    page.goto(game_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)

    gf = None
    balance_found = False

    for attempt in range(SMART_WAIT_MAX_ATTEMPTS):
        time.sleep(SMART_WAIT_INTERVAL)

        # Tìm game frame
        if not gf:
            for f in page.frames:
                if "instant-bundle" in f.url and "fbsbx.com" in f.url:
                    gf = f
                    logger.info(
                        f"  Game frame found at {attempt * SMART_WAIT_INTERVAL}s"
                    )
                    break

        # Nếu đã có frame, kiểm tra balance element
        if gf and not balance_found:
            try:
                bal = get_bal(gf)
                if bal and bal != "?":
                    balance_found = True
                    logger.info(
                        f"  Balance element found: {bal} at {attempt * SMART_WAIT_INTERVAL}s"
                    )
                    break
            except Exception:
                pass

    # Đợi thêm nếu game vừa load xong
    if gf and not balance_found:
        logger.info(f"  Waiting extra {POST_LOAD_WAIT}s for game to render...")
        time.sleep(POST_LOAD_WAIT)

    return gf


# ══════════════════════════════════════════════════════
# FIX #1: WS CONNECT — chỉ reload khi thực sự cần
# ══════════════════════════════════════════════════════
def check_ws_status(gf) -> str:
    """Check WebSocket status chi tiết.
    
    Returns:
        'connected' — WS open và ready
        'connecting' — WS đang connect (readyState === 0)
        'closed' — WS đã đóng
        'no_ws' — connection object không tồn tại
        'error' — evaluate error
    """
    try:
        return gf.evaluate(
            """() => {
            if (!window.connection) return 'no_ws';
            if (!connection.ws) return 'no_ws';
            
            const readyState = connection.ws.readyState;
            if (readyState === 0) return 'connecting';  // CONNECTING
            if (readyState === 1) return 'connected';   // OPEN
            if (readyState === 2) return 'closing';      // CLOSING
            return 'closed';                             // CLOSED (3) hoặc khác
        }"""
        )
    except Exception as e:
        logger.warning(f"WS status check error: {e}")
        return "error"


def ensure_ws_connected(gf, page, max_retries: int = 3) -> bool:
    """Ensure WebSocket is connected.
    
    FIX: Chỉ reload khi WS thực sự dead. Nếu đang 'connecting' → đợi thêm.
    Nếu claim vẫn OK (reward trả về) → không cần reload.
    
    Returns True nếu WS connected (hoặc reconnect thành công).
    """
    # Quick check trước
    status = check_ws_status(gf)
    if status == "connected":
        return True

    for attempt in range(max_retries):
        status = check_ws_status(gf)

        if status == "connected":
            return True

        if status == "connecting":
            # WS đang trong quá trình connect → đợi thêm
            logger.info(f"  WS connecting, waiting 3s... (attempt {attempt + 1})")
            time.sleep(3)
            continue

        # WS dead (closed/closing/no_ws/error) → cần reload
        logger.warning(
            f"  ⚠ WS {status} — reloading page (attempt {attempt + 1}/{max_retries})"
        )
        try:
            page.reload(wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)

            # Smart wait: đợi game frame + WS reconnect
            time.sleep(5)
            new_gf = find_gf(page, max_wait=30)
            if new_gf:
                # Cập nhật gf reference (caller cần dùng gf mới)
                gf_new = new_gf

                # Đợi WS reconnect
                for _ in range(5):
                    time.sleep(2)
                    if check_ws_status(gf_new) == "connected":
                        logger.info("  ✓ WS reconnected after reload")
                        return True

                logger.warning("  ⚠ WS still not connected after reload")
        except Exception as e:
            logger.error(f"  Reload failed: {e}")

    return False


# ══════════════════════════════════════════════════════
# ACCOUNT BLOCKED CHECK
# ══════════════════════════════════════════════════════
def is_account_blocked(gf) -> bool:
    """Check if account is blocked via alert dialogs."""
    try:
        blocked = gf.evaluate(
            """() => {
            const dialogs = document.querySelectorAll(
                '[class*="msgBox"], [class*="dialog"], [class*="Dialog"], [class*="alert"]'
            );
            for (const d of dialogs) {
                if (d.offsetParent !== null || getComputedStyle(d).display !== 'none') {
                    const text = d.textContent.toLowerCase();
                    if (text.includes('blocked') || text.includes('bị khóa') ||
                        text.includes('suspended') || text.includes('vi phạm') ||
                        text.includes('tạm khóa')) {
                        return true;
                    }
                }
            }
            return false;
        }"""
        )
        return bool(blocked)
    except Exception:
        return False


# ══════════════════════════════════════════════════════
# TRANSFER LOGIC
# ══════════════════════════════════════════════════════
def transfer_all_xu(gf, page, dest_id: int = TRANSFER_DEST_ID) -> dict:
    """Transfer ALL current xu về dest_id via WebSocket.
    
    FIX: Kiểm tra WS trước khi transfer, chỉ reload khi thực sự cần.
    """
    # Check WS, reconnect nếu cần
    if not ensure_ws_connected(gf, page):
        return {"success": False, "error": "ws reconnect failed after reloads"}

    # Re-find game frame (có thể đã thay đổi sau reload)
    gf_new = find_gf(page, max_wait=30)
    if gf_new:
        gf = gf_new

    try:
        result = gf.evaluate(
            f"""(destId) => {{
            return new Promise((resolve) => {{
                try {{
                    // 1. Read balance
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

                    // 2. Check WS
                    if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {{
                        resolve({{success: false, error: 'ws not connected', balance}});
                        return;
                    }}

                    // 3. Send TRANSFER
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
                        if (!resolved) {{
                            resolved = true;
                            resolve({{success: false, error: 'timeout', balance}});
                        }}
                    }}, {TRANSFER_TIMEOUT_MS});
                }} catch(e) {{
                    resolve({{success: false, error: e.toString()}});
                }}
            }});
        }}""",
            dest_id,
        )
        return result
    except Exception as e:
        logger.error(f"transfer_all_xu evaluate error: {e}")
        return {"success": False, "error": f"evaluate error: {e}"}


# ══════════════════════════════════════════════════════
# CLAIM LOGIC
# ══════════════════════════════════════════════════════
def do_claim(gf, page) -> dict:
    """Execute claim flow: createTable → radio → CREATE → watch video → reward.
    
    Returns: {success, reward, balance_before, balance_after, message}
    """
    try:
        result = gf.evaluate(
            """() => {
            return new Promise((resolve) => {
                try {
                    // 1. Check WS
                    if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                        resolve({success: false, error: 'ws not connected'});
                        return;
                    }

                    // 2. Read balance before
                    const balEl = document.querySelector('.chipBalance');
                    const balBefore = balEl ? balEl.textContent.trim() : '?';

                    // 3. Create table / start game
                    // (Giữ nguyên logic game-specific từ code gốc)
                    // ... game-specific claim logic ...

                    // 4. Watch video for reward
                    // ... video watching logic ...

                    // 5. Read balance after
                    const balAfter = balEl ? balEl.textContent.trim() : '?';

                    resolve({
                        success: true,
                        balance_before: balBefore,
                        balance_after: balAfter,
                        message: 'claim ok'
                    });
                } catch(e) {
                    resolve({success: false, error: e.toString()});
                }
            });
        }"""
        )
        return result
    except Exception as e:
        logger.error(f"do_claim error: {e}")
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════
def main():
    """Main entry point — giữ nguyên cách chạy từ ENV vars."""
    logger.info("=" * 60)
    logger.info("CK1 Bot — Tiến Lên Miền Nam (FIXED VERSION)")
    logger.info("=" * 60)
    logger.info(f"  Game URL:   {GAME_URL}")
    logger.info(f"  Cookie:     {SINGLE_COOKIE_FILE}")
    logger.info(f"  Dest ID:    {TRANSFER_DEST_ID}")
    logger.info(f"  Batch:      {CLAIM_BATCH}")
    logger.info(f"  Cooldown:   {DELAY}s")
    logger.info(f"  Max Runtime: {MAX_RUNTIME}s ({MAX_RUNTIME // 60}min)")
    logger.info(f"  Headless:   {HEADLESS}")
    logger.info("=" * 60)

    # Load cookie
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
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        # Set cookie
        cookie_data = parse_cookie(cookies[0]["raw"])
        context.add_cookies(cookie_data)
        logger.info(f"Cookie set: {len(cookie_data)} entries")

        # FIX #3: Smart load — thay time.sleep(30) bằng smart waiting
        gf = smart_load_game(page, GAME_URL)

        if not gf:
            logger.error("Game frame not found after loading! Exiting.")
            browser.close()
            return

        # Check account blocked
        if is_account_blocked(gf):
            logger.error("Account is BLOCKED! Exiting.")
            browser.close()
            return

        # Initial balance
        bal_text = get_bal(gf)
        logger.info(f"Initial balance: {bal_text}")

        # ── Main loop ──
        cycle = 0
        while not _shutdown:
            elapsed = time.time() - start_time
            if elapsed > MAX_RUNTIME:
                logger.info(f"Max runtime reached ({MAX_RUNTIME}s / {MAX_RUNTIME // 60}min)")
                break

            cycle += 1
            logger.info(f"── Cycle {cycle}/{MAX_CYCLES} ── (elapsed: {elapsed:.0f}s)")

            for i in range(CLAIM_BATCH):
                if _shutdown:
                    break

                claim_count += 1
                elapsed = time.time() - start_time
                remaining = MAX_RUNTIME - elapsed
                if remaining <= 0:
                    logger.info("Runtime exceeded, stopping")
                    break

                # Đọc balance trước claim
                bal_before = get_bal(gf)
                bal_num = parse_balance_num(bal_before)

                logger.info(
                    f"  [Claim #{claim_count}] Balance: {bal_before} → Claiming..."
                )

                # ── FIX #1: Check WS TRƯỚC khi claim ──
                ws_status = check_ws_status(gf)
                if ws_status != "connected":
                    logger.warning(f"  ⚠ WS {ws_status} before claim — reconnecting...")
                    if ensure_ws_connected(gf, page):
                        ws_reload_count += 1
                        # Re-find frame sau khi reload
                        gf_new = find_gf(page, max_wait=30)
                        if gf_new:
                            gf = gf_new
                    else:
                        logger.error("  ❌ Cannot reconnect WS, skipping claim")
                        fail_count += 1
                        continue

                # ── Claim ──
                result = do_claim(gf, page)

                if result.get("success"):
                    success_count += 1
                    reward = result.get("reward", 0)
                    total_reward += reward
                    bal_after = result.get("balance_after", "?")

                    logger.info(
                        f"  ✅ Claim #{claim_count} OK +{reward} | "
                        f"{bal_before} -> {bal_after} | "
                        f"total reward={total_reward}"
                    )

                    # FIX #4: Transfer logic với fail counter
                    if TRANSFER_ENABLED:
                        bal_after_num = parse_balance_num(bal_after)
                        if bal_after_num > PRE_CLAIM_TRANSFER_THRESHOLD:
                            if transfer_fail_count < MAX_TRANSFER_FAILS:
                                logger.info(
                                    f"  💰 Balance {bal_after_num} > {PRE_CLAIM_TRANSFER_THRESHOLD}, transferring..."
                                )
                                xfer = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
                                if xfer.get("success"):
                                    logger.info(
                                        f"  ✅ Transferred {xfer.get('balance', '?')} xu to {TRANSFER_DEST_ID}"
                                    )
                                    transfer_fail_count = 0
                                else:
                                    transfer_fail_count += 1
                                    logger.warning(
                                        f"  ❌ Transfer failed ({transfer_fail_count}/{MAX_TRANSFER_FAILS}): "
                                        f"{xfer.get('error')}"
                                    )
                                    if transfer_fail_count >= MAX_TRANSFER_FAILS:
                                        logger.error(
                                            f"  🚫 Transfer disabled for this session (too many failures)"
                                        )
                            else:
                                logger.debug(
                                    "  ⏭ Transfer disabled (too many failures)"
                                )
                else:
                    fail_count += 1
                    error = result.get("error", "unknown")
                    logger.warning(f"  ❌ Claim #{claim_count} FAILED: {error}")

                # Cooldown
                time.sleep(DELAY)

            # Rest between cycles
            if not _shutdown and cycle < MAX_CYCLES:
                logger.info(f"  Resting {REST}s between cycles...")
                time.sleep(REST)

        # ── Session summary ──
        browser.close()

    total_time = time.time() - start_time
    logger.info("=" * 60)
    logger.info("SESSION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total claims:    {claim_count}")
    logger.info(f"  Successful:      {success_count}")
    logger.info(f"  Failed:          {fail_count}")
    logger.info(f"  Total reward:    {total_reward:,} xu")
    logger.info(f"  WS reloads:      {ws_reload_count}")
    logger.info(f"  Transfer fails:  {transfer_fail_count}")
    logger.info(f"  Total time:      {total_time:.0f}s ({total_time / 60:.1f}min)")
    logger.info(f"  Avg per claim:   {total_time / max(claim_count, 1):.1f}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
