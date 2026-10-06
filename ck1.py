#!/usr/bin/env python3
"""FB Tien Len Mien Nam reward bot v9 — FIXED VERSION
★ Giữ nguyên claim logic gốc + fix: find_gf, WS, balance, logging

FIXES:
  1. find_gf: max(1, max_wait//5) — luôn check ít nhất 1 lần
  2. ensure_ws_connected: trả về (bool, new_gf) — caller cập nhật frame
  3. Balance: thêm fallback selectors
  4. Logging: thay print() bằng logging module
  5. Graceful shutdown: signal handler
"""

import os, sys, time, re, signal, logging

# ═══════════════ LOGGING ═══════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ck1")

# Thử import module bổ trợ nếu có (không bắt buộc)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

GAME_URL = "https://www.facebook.com/gaming/play/tienlen_miennam"
CLAIM_BATCH = int(os.environ.get("CLAIM_BATCH", "40"))  # Số claim trước khi transfer
MAX_CYCLES = CLAIM_BATCH
DELAY = float(os.environ.get("COOLDOWN", "3"))
REST = int(os.environ.get("REST_BETWEEN_RUNS", "3"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

# ============ TRANSFER LOGIC ============
TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "51977054"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"

# ============ SINGLE COOKIE MODE ============
SINGLE_COOKIE_FILE = os.environ.get("SINGLE_COOKIE_FILE", "ck1.txt").strip()

# ============ Pre-claim transfer threshold ============
PRE_CLAIM_TRANSFER_THRESHOLD = int(os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000"))

# ============ GRACEFUL SHUTDOWN ============
_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    logger.warning(f"Received signal {signum}, shutting down...")
    _shutdown = True

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def parse_balance_num(bal_text):
    """Parse '56.4k' or '123,456' or '78900' → int."""
    if not bal_text or bal_text == '?':
        return 0
    s = str(bal_text).strip().lower().replace(',', '').replace(' ', '')
    try:
        if s.endswith('k'):
            return int(float(s[:-1]) * 1000)
        if s.endswith('m'):
            return int(float(s[:-1]) * 1000000)
        return int(float(s))
    except Exception:
        return 0


# ============================================================
# ĐỌC COOKIE TỪ FILE DUY NHẤT
# ============================================================
def load_single_cookie_set(path):
    """Đọc đúng 1 file cookie. Trả về [{"file": "...", "raw": "..."}] hoặc []."""
    if not os.path.exists(path):
        logger.error(f"Không tìm thấy file: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
    except Exception as e:
        logger.error(f"Lỗi đọc {path}: {e}")
        return []
    if not content:
        logger.error(f"{path} rỗng")
        return []
    content = content.strip('"').strip("'")
    content = " ".join(content.split())
    content = content.replace(";  ", "; ").replace(" ;", ";")
    logger.info(f"Nạp {os.path.basename(path)} ({len(content)} ký tự)")
    return [{"file": os.path.basename(path), "raw": content}]


def parse_cookie(raw: str):
    """Parse chuỗi cookie header thành list dict cho Playwright."""
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
        {"name": n, "value": mv.value, "domain": ".facebook.com",
         "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
        for n, mv in parsed.items() if n and mv.value
    ]


# ============================================================
# HELPER — ★ FIX: Thêm fallback selectors cho balance
# ============================================================
def get_bal(gf):
    """★ FIX: Thử nhiều selectors thay vì chỉ 1."""
    try:
        return gf.evaluate(r"""() => {
            // Thử selector gốc trước
            var el = document.querySelector('.chipBalance');
            if (el) {
                var t = el.textContent.trim();
                if (t && t !== '?' && /d/.test(t)) return t;
            }
            // Fallback selectors
            var sels = ['.balance', '.chip-count', '.coin-balance',
                '.coinBalance', '[data-balance]', '[data-chip]',
                '.game-balance', '.player-balance'];
            for (var i = 0; i < sels.length; i++) {
                var el2 = document.querySelector(sels[i]);
                if (el2) {
                    var t2 = el2.textContent.trim();
                    if (t2 && t2 !== '?' && /d/.test(t2)) return t2;
                }
            }
            return '?';
        }""")
    except Exception:
        return "?"


def transfer_all_xu(gf, page, dest_id=TRANSFER_DEST_ID):
    """Transfer ALL current xu về dest_id via game's connection.send.
    ★ FIX: Nhận gf mới từ ensure_ws_connected.
    """
    # ★ FIX: ensure_ws_connected giờ trả (bool, new_gf)
    ws_ok, new_gf = ensure_ws_connected(gf, page)
    if new_gf:
        gf = new_gf
    if not ws_ok:
        return {"success": False, "error": "ws reconnect failed after reloads"}

    try:
        result = gf.evaluate("""(destId) => {
            return new Promise((resolve) => {
                try {
                    const balEl = document.querySelector('.chipBalance');
                    const balText = balEl ? balEl.textContent.trim() : '0';
                    let balance = 0;
                    const cleaned = balText.replace(/[^0-9kK.]/g, '');
                    if (cleaned.toLowerCase().endsWith('k')) {
                        balance = Math.round(parseFloat(cleaned.slice(0, -1)) * 1000);
                    } else if (cleaned) {
                        balance = parseInt(cleaned) || 0;
                    }
                    if (balance < 200) {
                        resolve({success: false, error: 'balance < 200', balance: balance});
                        return;
                    }
                    if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                        resolve({success: false, error: 'ws not connected', balance: balance});
                        return;
                    }
                    const msg = new OutboundMessage("TRANSFER");
                    msg.writeLong(destId);
                    msg.writeLong(balance);
                    let resolved = false;
                    connection.send(msg, function(resp, ok) {
                        if (resolved) return;
                        resolved = true;
                        try {
                            const status = resp.readSignedByte();
                            const txt = resp.readUtf16String ? resp.readUtf16String() : '';
                            resolve({success: ok, status: status, message: txt, balance: balance, dest: destId});
                        } catch(e) {
                            resolve({success: ok, error: e.toString(), balance: balance});
                        }
                    });
                    setTimeout(() => {
                        if (!resolved) {
                            resolved = true;
                            resolve({success: false, error: 'timeout', balance: balance});
                        }
                    }, 12000);
                } catch(e) {
                    resolve({success: false, error: e.toString()});
                }
            });
        }""", dest_id)
        return result
    except Exception as e:
        return {"success": False, "error": f"evaluate error: {e}"}


# ★ FIX #1: find_gf — luôn check ít nhất 1 lần
def find_gf(page, max_wait=120):
    """Find game frame. ★ FIX: max(1, ...) đảm bảo luôn check ít nhất 1 lần."""
    # ★ FIX: range(0) = empty loop → dùng max(1, ...)
    iterations = max(1, max_wait // 5) if max_wait > 0 else 1
    sleep_time = 5 if max_wait > 0 else 0

    for attempt in range(iterations):
        for f in page.frames:
            if "instant-bundle" in f.url and "fbsbx.com" in f.url:
                return f
        if sleep_time > 0 and attempt < iterations - 1:
            time.sleep(sleep_time)
    return None


def is_account_blocked(gf):
    """Check if any visible alert dialog says account is blocked."""
    try:
        blocked = gf.evaluate("""() => {
            const dialogs = document.querySelectorAll('[class*="msgBox"], [class*="dialog"], [class*="Dialog"], [class*="alert"]');
            for (const d of dialogs) {
                if (d.offsetParent === null) continue;
                const txt = (d.textContent || '').toLowerCase();
                if (txt.includes('blocked') || txt.includes('khóa') || txt.includes('cấm')) {
                    return true;
                }
            }
            return false;
        }""")
        return bool(blocked)
    except Exception:
        return False


# ★ FIX #2: ensure_ws_connected — trả về (bool, new_gf)
def ensure_ws_connected(gf, page, max_retries=2):
    """Check WS state, reload page if disconnected.
    ★ FIX: Trả về (bool, new_gf) để caller cập nhật frame reference.
    """
    try:
        ws_ok = gf.evaluate("() => !!(window.connection && connection.ws && connection.ws.readyState === 1)")
        if ws_ok:
            return True, gf  # ★ Trả về gf hiện tại
    except Exception:
        pass

    logger.warning("  ⚠ WS not connected — reloading page...")
    for retry in range(max_retries):
        try:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(20000)  # 20s for game to load
            # ★ FIX: find_gf giờ luôn check ít nhất 1 lần
            new_gf = find_gf(page, max_wait=60)
            if not new_gf:
                logger.warning(f"  ⚠ Reload #{retry+1}: game frame not found")
                continue
            # Wait for WS connection
            for ws_check in range(15):  # 45s wait
                try:
                    ws_ok = new_gf.evaluate("() => !!(window.connection && connection.ws && connection.ws.readyState === 1)")
                    if ws_ok:
                        logger.info(f"  ✓ WS reconnected after reload #{retry+1}")
                        return True, new_gf  # ★ Trả về MỚI gf!
                except:
                    pass
                page.wait_for_timeout(3000)
        except Exception as e:
            logger.error(f"  ⚠ Reload #{retry+1} error: {e}")

    logger.error(f"  ❌ WS reconnect failed after {max_retries} reloads")
    return False, None  # ★ Trả về None nếu fail


def trigger_and_claim(gf, page):
    """★ GIỮ NGUYÊN LOGIC GỐC — Flow:
      1. ensure_ws_connected (reload if dead)
      2. createTable()
      3. Select radio_11 (game mode)
      4. Click input[name="CREATE"] (submit)
      5. If "not enough coin" alert → click "Watch video" button
      6. Send OutboundMessage("VIDEO_REWARD") → server returns amount
      7. Retry once if first attempt fails
    """
    # ★ FIX: Nhận (bool, new_gf) từ ensure_ws_connected
    ws_ok, new_gf = ensure_ws_connected(gf, page, max_retries=1)
    if new_gf:
        gf = new_gf
    if not ws_ok:
        return {"success": False, "error": "ws reconnect failed"}

    try:
        gf.evaluate("createTable()")
    except Exception:
        pass
    time.sleep(2)

    try:
        gf.evaluate("""() => {
            const r = document.getElementById('radio_11');
            if (r) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }
        }""")
    except Exception:
        pass
    time.sleep(0.5)

    try:
        gf.evaluate("""() => {
            const b = document.querySelector('input[name="CREATE"]');
            if (b) b.click();
        }""")
    except Exception:
        pass
    time.sleep(3)

    alert_clicked = False
    try:
        alert_clicked = gf.evaluate("""() => {
            const dialogs = document.querySelectorAll('[class*="msgBox"]');
            for (const d of dialogs) {
                if (d.offsetParent !== null && d.textContent.includes('enough coin')) {
                    const buttons = d.querySelectorAll('input[type="button"], button');
                    for (const b of buttons) {
                        const val = (b.value || b.textContent || '').toLowerCase();
                        if (val.includes('watch') || val.includes('video')) {
                            b.click();
                            return true;
                        }
                    }
                }
            }
            return false;
        }""")
    except Exception:
        pass

    if alert_clicked:
        time.sleep(2)

    # Retry logic: try + 1 retry = 2 total attempts
    max_attempts = 2
    timeout_ms = 15000
    result = None

    for attempt in range(max_attempts):
        try:
            result = gf.evaluate(f"""() => {{
                return new Promise((resolve) => {{
                    try {{
                        if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {{
                            resolve({{success: false, error: 'ws not connected'}});
                            return;
                        }}
                        const msg = new OutboundMessage("VIDEO_REWARD");
                        msg.writeByte(1);
                        let resolved = false;
                        connection.send(msg, function(response, success) {{
                            if (resolved) return;
                            resolved = true;
                            if (success) {{
                                try {{
                                    const amount = response.readLong();
                                    if (window.Ads && window.Ads.RewardedVideo) {{
                                        window.Ads.RewardedVideo.videoIndex++;
                                        if (window.Ads.RewardedVideo.updateRewardButton)
                                            window.Ads.RewardedVideo.updateRewardButton();
                                    }}
                                    resolve({{success: true, amount: amount}});
                                }} catch(e) {{
                                    resolve({{success: true, amount: 0, error: e.toString()}});
                                }}
                            }} else {{
                                resolve({{success: false, error: 'no response'}});
                            }}
                        }});
                        setTimeout(() => {{
                            if (!resolved) {{ resolved = true; resolve({{success: false, error: 'timeout'}}); }}
                        }}, {timeout_ms});
                    }} catch(e) {{
                        resolve({{success: false, error: e.toString()}});
                    }}
                }});
            }}""")
        except Exception as e:
            result = {"success": False, "error": f"evaluate error: {e}"}

        # Check result — if success, break
        if result.get('success') and result.get('amount', 0) > 0:
            break

        # Retry logic
        if attempt < max_attempts - 1:
            err = result.get('error', 'unknown')
            logger.warning(f"  attempt {attempt+1}/{max_attempts}: FAIL ({err}), retrying...")
            try:
                gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
            except:
                pass
            time.sleep(2)

            # ★ FIX: Nhận (bool, new_gf)
            ws_ok2, new_gf2 = ensure_ws_connected(gf, page, max_retries=1)
            if new_gf2:
                gf = new_gf2
            if not ws_ok2:
                logger.warning(f"  WS still dead, skip retry")
                break

            # Re-click watch video button
            try:
                gf.evaluate("""() => {
                    const dialogs = document.querySelectorAll('[class*="msgBox"]');
                    for (const d of dialogs) {
                        if (d.offsetParent !== null && d.textContent.includes('enough coin')) {
                            const buttons = d.querySelectorAll('input[type="button"], button');
                            for (const b of buttons) {
                                const val = (b.value || b.textContent || '').toLowerCase();
                                if (val.includes('watch') || val.includes('video')) {
                                    b.click();
                                    return true;
                                }
                            }
                        }
                    }
                    return false;
                }""")
            except:
                pass
            time.sleep(1)
        else:
            err = result.get('error', 'unknown')
            logger.warning(f"  attempt {attempt+1}/{max_attempts}: FAIL ({err}) — giving up")

    if not result.get('success') or result.get('amount', 0) == 0:
        result['method'] = 'alert_clicked' if alert_clicked else 'no_alert'
    return result


# ============================================================
# CONTINUOUS SESSION — ★ FIX: Cập nhật gf sau mỗi ensure_ws
# ============================================================
def run_continuous_session(p, fb_cookies, session_id, started_at):
    """Mở browser → login FB → load game → (claim → transfer → ...) LIÊN TỤC."""
    logger.info(f"########## SESSION {session_id} - CONTINUOUS MODE ##########")

    browser = p.chromium.launch(
        headless=HEADLESS,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080}, locale="en-US",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/139.0.0.0 Safari/537.36",
    )
    try:
        for c in fb_cookies:
            c['domain'] = '.facebook.com'
        context.add_cookies(fb_cookies)
    except Exception as e:
        logger.error(f"add_cookies error: {e}")
        try: browser.close()
        except: pass
        return 0, 0, 0, False

    page = context.new_page()

    # ===== [1] Login FB — 1 LẦN =====
    logger.info("[1] Login FB...")
    try:
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.error(f"goto FB error: {e}")
        try: browser.close()
        except: pass
        return 0, 0, 0, False

    page.wait_for_timeout(5000)
    try:
        if page.locator('input[placeholder="Email or phone"]').count() > 0:
            logger.error("Not logged in (cookie hết hạn?)")
            try: browser.close()
            except: pass
            return 0, 0, 0, False
    except Exception:
        pass
    logger.info("  Login OK")

    # ===== [2] Open game — 1 LẦN =====
    logger.info("[2] Open game...")
    try:
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        logger.error(f"goto game error: {e}")
        try: browser.close()
        except: pass
        return 0, 0, 0, True

    page.wait_for_timeout(20000)

    # ★ FIX: find_gf giờ luôn check ít nhất 1 lần
    gf = find_gf(page, max_wait=60)
    if not gf:
        logger.error("Game frame not found")
        try: browser.close()
        except: pass
        return 0, 0, 0, True

    logger.info("  Game loaded")
    page.wait_for_timeout(10000)

    # ===== [3] Wait WS — 1 LẦN =====
    logger.info("[3] Wait WS...")
    for _ in range(10):
        try:
            if gf.evaluate("() => window.connection && connection.ws && connection.ws.readyState === 1"):
                logger.info("  WS connected")
                break
        except Exception:
            pass
        time.sleep(3)

    # ===== Check blocked =====
    if is_account_blocked(gf):
        logger.error("❌ ACCOUNT BLOCKED — skipping")
        try:
            gf.evaluate("""() => {
                const btns = document.querySelectorAll('input[type="button"], button');
                for (const b of btns) {
                    const t = (b.value || b.textContent || '').toLowerCase().trim();
                    if (t === 'ok' || t === 'đóng' || t === 'close') b.click();
                }
            }""")
        except: pass
        try: browser.close()
        except: pass
        return 0, 0, 0, False

    bal_start = get_bal(gf)
    logger.info(f"  Balance: {bal_start}")

    # ===== Pre-claim transfer =====
    bal_start_num = parse_balance_num(bal_start)
    if TRANSFER_ENABLED and bal_start_num > PRE_CLAIM_TRANSFER_THRESHOLD:
        logger.info(f"[Pre-claim] Balance {bal_start_num:,} > {PRE_CLAIM_TRANSFER_THRESHOLD:,}, transferring...")
        try:
            pre_result = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
            if pre_result.get('success'):
                amt = pre_result.get('balance', 0)
                logger.info(f"  ✅ Pre-claim transfer: {amt:,} xu → {TRANSFER_DEST_ID}")
                time.sleep(2)
                bal_start = get_bal(gf)
                logger.info(f"     Balance after: {bal_start}")
            else:
                logger.warning(f"  ❌ Pre-claim transfer fail: {pre_result.get('error')}")
        except Exception as e:
            logger.error(f"  ❌ Pre-claim transfer exception: {e}")
    elif bal_start_num > 0:
        logger.info(f"  (Balance {bal_start_num:,} ≤ threshold, skip pre-claim transfer)")

    # ===== [4] BATCH LOOP =====
    logger.info(f"[4] BATCH MODE: claim {CLAIM_BATCH} → transfer → repeat...")
    total_reward = 0
    total_transferred = 0
    ok = 0
    fail = 0
    claim_count = 0

    while True:
        if _shutdown:
            logger.warning("Shutdown requested")
            break

        elapsed = time.time() - started_at
        if elapsed > MAX_RUNTIME:
            logger.info(f"Hết thời gian ({MAX_RUNTIME}s), dừng.")
            break

        # Pre-batch balance check
        bal_before_batch = get_bal(gf)
        bal_before_batch_num = parse_balance_num(bal_before_batch)
        if TRANSFER_ENABLED and bal_before_batch_num > PRE_CLAIM_TRANSFER_THRESHOLD:
            logger.info(f"[BATCH START] Balance: {bal_before_batch} → Pre-batch transfer...")
            try:
                pre_result = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
                if pre_result.get('success'):
                    logger.info(f"  ✅ Pre-batch transfer: {pre_result.get('balance', 0):,} xu")
                    time.sleep(2)
            except Exception as e:
                logger.error(f"  ❌ Pre-batch transfer fail: {e}")

        # Inner batch loop
        batch_num = claim_count // CLAIM_BATCH + 1
        logger.info(f"[Claim Batch #{batch_num}] Starting {CLAIM_BATCH} claims...")

        for batch_idx in range(CLAIM_BATCH):
            if _shutdown:
                break

            elapsed = time.time() - started_at
            if elapsed > MAX_RUNTIME:
                logger.info(f"Hết thời gian trong batch, dừng.")
                break

            bal_before = get_bal(gf)

            # Clean up old dialogs
            try:
                gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
            except Exception:
                pass
            time.sleep(1)

            # ===== CLAIM =====
            logger.info(f"  [Claim #{claim_count + batch_idx + 1}] Balance: {bal_before} → Claiming...")

            try:
                result = trigger_and_claim(gf, page)
            except Exception as e:
                logger.error(f"    EXCEPTION ({e})")
                fail += 1
                if fail >= 8:
                    break
                time.sleep(DELAY)
                continue

            if result.get('success') and result.get('amount', 0) > 0:
                amount = result['amount']
                total_reward += amount
                ok += 1
                claim_count += 1
                fail = 0
                time.sleep(1)
                bal_after_claim = get_bal(gf)
                logger.info(f"    ✅ Claim #{claim_count} OK +{amount} | {bal_before} -> {bal_after_claim} | total reward={total_reward}")
            else:
                fail += 1
                err = result.get('error', 'unknown')
                method = result.get('method', '')
                logger.warning(f"    ❌ Claim FAIL ({err}) [{method}] | {bal_before}")

            if fail >= 8:
                logger.warning("Too many fails, stopping batch")
                break

            time.sleep(DELAY)

        if fail >= 8:
            break

        # ===== TRANSFER sau batch =====
        bal_after_batch = get_bal(gf)
        bal_after_batch_num = parse_balance_num(bal_after_batch)

        if TRANSFER_ENABLED and bal_after_batch_num > 200:
            logger.info(f"[Transfer] Balance: {bal_after_batch} → Transferring...")
            try:
                transfer_result = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
                if transfer_result.get('success'):
                    amt = transfer_result.get('balance', 0)
                    total_transferred += amt
                    logger.info(f"  ✅ Transferred {amt:,} xu → {TRANSFER_DEST_ID}")
                    time.sleep(2)
                    bal_after_transfer = get_bal(gf)
                    logger.info(f"     Balance after: {bal_after_transfer}")
                else:
                    logger.warning(f"  ❌ Transfer FAIL: {transfer_result.get('error')}")
            except Exception as e:
                logger.error(f"  ❌ Transfer exception: {e}")
        else:
            logger.info(f"  ⚠ Balance {bal_after_batch_num} ≤ 200, skip transfer")

        time.sleep(DELAY)

    logger.info(f"[SESSION {session_id}] Xong | claims OK={ok} fail={fail} | reward={total_reward:,} | transferred={total_transferred:,}")
    return total_reward, ok, fail, True


# ============================================================
# MAIN
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("FB Tien Len Mien Nam reward bot v9 — FIXED VERSION")
    logger.info("Claim và transfer LIÊN TỤC")
    logger.info("=" * 60)
    logger.info(f"Config: CLAIM_BATCH={CLAIM_BATCH} COOLDOWN={DELAY}s REST={REST}s TRANSFER_DEST={TRANSFER_DEST_ID}")
    logger.info("=" * 60)

    cookie_entries = load_single_cookie_set(SINGLE_COOKIE_FILE)
    if not cookie_entries:
        logger.error(f"Không nạp được cookie từ {SINGLE_COOKIE_FILE}")
        return 1

    entry = cookie_entries[0]
    fb_cookies = parse_cookie(entry["raw"])
    if not fb_cookies:
        logger.error(f"Cookie {entry['file']} parse rỗng")
        return 1

    logger.info(f"Đã parse {len(fb_cookies)} cookies từ {entry['file']}")

    started_at = time.time()
    session_id = 0
    grand_reward = 0
    grand_ok = 0
    grand_fail = 0

    with sync_playwright() as p:
        session_id += 1
        logger.info(f"[Session {session_id}] Starting at {time.strftime('%H:%M:%S')}")
        total, ok, fail, cookies_ok = run_continuous_session(p, fb_cookies, session_id, started_at)
        grand_reward += total
        grand_ok += ok
        grand_fail += fail
        logger.info(f"[Session {session_id}] Result: {ok} claims OK, {fail} fail")

    logger.info("=" * 60)
    logger.info(f"TỔNG: {session_id} session | {grand_ok} claims ok | {grand_fail} fail | reward={grand_reward:,}")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
