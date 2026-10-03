#!/usr/bin/env python3
"""FB Game reward bot v15 — URL game 2841623646051191 (Invasion 2021).
Cookie account 61595197311852. Full logging.
"""
import os, sys, time, json
from datetime import datetime

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright


def log(msg, tag=""):
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{ts}]"
    if tag:
        prefix += f" [{tag}]"
    print(f"{prefix} {msg}", flush=True)


# ============================================================
# >>> COOKIE — account 61595197311852 <<<
# ============================================================
COOKIE_RAW = (
    "sb=XSa_ahbAv9XMUHfep4z2jQUb; m_pixel_ratio=2; vpd=v1%3B616x360x2; "
    "ps_l=1; ps_n=1; datr=IdzAalcIPU3mOeQoeHo4Qdyo; "
    "pas=61595197311852%3APOwi1i3tVJ%2C61594782729357%3AVvbK8iGoqB%2C"
    "61594960651753%3Aci75sCyaff%2C61594746041618%3AiAAzWgyfvh%2C"
    "100051928670915%3Aw80kSunsKe%2C61561542347462%3AMdbf81FzjV%2C"
    "61562610920837%3A5TQgo8d28i; "
    "c_user=61595197311852; "
    "xs=43%3AbObftd0SQ41NwQ%3A2%3A1791026979%3A-1%3A-1; "
    "fr=0ZX5mgCABu4MTVFSz.AWctLZJb6K4_hw9XFaCu-XYuAOP67e-8zsX_rlom8pct6KZHMSg"
    ".BqvyZd..AAA.0.0.BqwOcq.AWePPR565PNwOsO5kpidAw2KPi4; "
    "locale=en_GB; "
    "fbl_st=101422426%3BT%3A29850449; "
    "wl_cbv=v2%3Bclient_version%3A3310%3Btimestamp%3A1791026986; "
    "wd=360x616"
)

# ============================================================
# >>> URL GAME MỚI — 2841623646051191 <<<
# ============================================================
GAME_URL = "https://www.facebook.com/gaming/play/2841623646051191/?context_source_id=&context_type=SOLO&payload=&source=game_switch"

# ============================================================
# CONFIG
# ============================================================
MAX_CYCLES = int(os.environ.get("MAX_CLAIMS", "40"))
DELAY = float(os.environ.get("COOLDOWN", "3"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", "600"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"
SLEEP_BETWEEN_RUNS = int(os.environ.get("SLEEP_BETWEEN_RUNS", "10"))

TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "51977054"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"
PRE_CLAIM_TRANSFER_THRESHOLD = int(
    os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000")
)

SHOT_DIR = os.environ.get("SHOT_DIR", ".")


# ============================================================
# PARSE COOKIE
# ============================================================
def parse_cookie(raw: str):
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


def cookie_summary(cookies):
    d = {c['name']: c['value'] for c in cookies}
    return {
        "count": len(cookies),
        "c_user": d.get('c_user', '?')[:20],
        "xs_prefix": d.get('xs', '?')[:20],
        "datr": d.get('datr', '?')[:20],
        "locale": d.get('locale', '?'),
        "wd": d.get('wd', '(none)'),
    }


# ============================================================
# HELPER
# ============================================================
def parse_balance_num(bal_text):
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


def get_bal(gf):
    try:
        return gf.evaluate(
            "() => document.querySelector('.chipBalance')?.textContent.trim() || '?'"
        )
    except Exception:
        return "?"


def get_page_url(page):
    try:
        return page.url
    except Exception:
        return "?"


def log_all_frames(page, tag=""):
    try:
        frames = page.frames
        log(f"  Có {len(frames)} frame:", tag)
        for i, f in enumerate(frames):
            url = f.url[:200] if f.url else "(empty)"
            log(f"    [{i}] {url}", tag)
    except Exception as e:
        log(f"  Lỗi log frames: {e}", tag)


def screenshot(page, name):
    try:
        path = os.path.join(SHOT_DIR, name)
        page.screenshot(path=path, full_page=False)
        log(f"  📸 Screenshot: {path}")
        return path
    except Exception as e:
        log(f"  ⚠ Không chụp được: {e}")
        return None


def find_gf(page, max_wait=120):
    """Tìm iframe game — match nhiều pattern."""
    start = time.time()
    last_log = 0
    for i in range(max_wait // 5):
        elapsed = int(time.time() - start)
        if elapsed - last_log >= 15:
            last_log = elapsed
            log(f"  ⏳ Đang tìm frame game... ({elapsed}s, {len(page.frames)} frame)")

        for f in page.frames:
            url = f.url
            # Match các pattern iframe game
            if "shield-apps-" in url and "fbsbx.com" in url:
                log(f"  ✓ Tìm thấy game frame (shield-apps) sau {int(time.time()-start)}s")
                log(f"    URL: {url[:150]}")
                return f
            if "apps-" in url and "fbsbx.com" in url:
                log(f"  ✓ Tìm thấy game frame (apps-) sau {int(time.time()-start)}s")
                log(f"    URL: {url[:150]}")
                return f
            if "instant-bundle" in url and "fbsbx.com" in url:
                log(f"  ✓ Tìm thấy game frame (instant-bundle) sau {int(time.time()-start)}s")
                return f
            if "fb.gg" in url and f != page.main_frame:
                log(f"  ✓ Tìm thấy game frame (fb.gg) sau {int(time.time()-start)}s")
                return f
        time.sleep(5)

    log(f"  ✗ Hết {max_wait}s không tìm thấy game frame")
    return None


def is_account_blocked(gf):
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


def dismiss_popups(page):
    clicked = 0
    for _ in range(3):
        try:
            found = page.evaluate("""() => {
                const keywords = ['đồng ý', 'chấp nhận', 'ok', 'continue', 'accept',
                                  'allow', 'cho phép', 'đóng', 'close', 'got it',
                                  'bắt đầu', 'start', 'chơi ngay', 'play now'];
                const btns = document.querySelectorAll('button, [role="button"], a[role="button"]');
                let count = 0;
                for (const b of btns) {
                    if (b.offsetParent === null) continue;
                    const t = (b.textContent || '').toLowerCase().trim();
                    for (const kw of keywords) {
                        if (t === kw || t.includes(kw)) {
                            try { b.click(); count++; } catch(e) {}
                            break;
                        }
                    }
                }
                return count;
            }""")
            if found:
                clicked += found
                page.wait_for_timeout(1500)
            else:
                break
        except Exception:
            break
    if clicked:
        log(f"  Đã đóng {clicked} popup/button")
    return clicked


# ============================================================
# TRANSFER
# ============================================================
def transfer_all_xu(gf, page, dest_id=TRANSFER_DEST_ID):
    log(f"  → Bắt đầu transfer tới {dest_id}...")
    t0 = time.time()
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
                    if (!window.connection || typeof connection.send !== 'function') {
                        resolve({success: false, error: 'no connection.send', balance: balance});
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
        elapsed = int((time.time() - t0) * 10) / 10
        log(f"  ← Transfer xong sau {elapsed}s: {json.dumps(result, ensure_ascii=False)[:200]}")
        return result
    except Exception as e:
        log(f"  ✗ Transfer exception: {e}")
        return {"success": False, "error": f"evaluate error: {e}"}


# ============================================================
# CLAIM
# ============================================================
def trigger_and_claim(gf):
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

    max_attempts = 2
    timeout_ms = 15000
    result = None
    for attempt in range(max_attempts):
        try:
            result = gf.evaluate(f"""() => {{
                return new Promise((resolve) => {{
                    try {{
                        if (!window.connection || typeof connection.send !== 'function') {{
                            resolve({{success: false, error: 'no connection.send'}});
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
                                resolve({{success: false, error: 'send returned false'}});
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

        if result.get('success') and result.get('amount', 0) > 0:
            break

        if attempt < max_attempts - 1:
            err = result.get('error', 'unknown')
            log(f"    attempt {attempt+1}/{max_attempts}: FAIL ({err}), retrying...")
            try:
                gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
            except Exception:
                pass
            time.sleep(2)
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
            except Exception:
                pass
            time.sleep(1)

    if result and (not result.get('success') or result.get('amount', 0) == 0):
        result['method'] = 'alert_clicked' if alert_clicked else 'no_alert'

    return result or {"success": False, "error": "no result"}


# ============================================================
# SESSION
# ============================================================
def run_one_session(p, fb_cookies, session_id, started_at):
    session_t0 = time.time()
    log("=" * 60)
    log(f"########## SESSION {session_id} ##########")
    log("=" * 60)

    log("[LAUNCH] Khởi tạo browser...")
    try:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
    except Exception as e:
        log(f"  ✗ Launch error: {e}")
        return 0, 0, 0, False

    log(f"  ✓ Browser OK sau {int((time.time()-session_t0)*10)/10}s")

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080}, locale="en-US",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/139.0.0.0 Safari/537.36",
    )
    log("  ✓ Context OK")

    log(f"[COOKIE] Thêm {len(fb_cookies)} cookie...")
    try:
        for c in fb_cookies:
            c['domain'] = '.facebook.com'
        context.add_cookies(fb_cookies)
        log("  ✓ add_cookies OK")
    except Exception as e:
        log(f"  ✗ add_cookies error: {e}")
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    page = context.new_page()
    log("  ✓ Page OK")

    # Login
    log("[1] Login FB...")
    try:
        page.goto("https://www.facebook.com/",
                  wait_until="domcontentloaded", timeout=30000)
        log(f"  ✓ goto FB OK")
    except Exception as e:
        log(f"  ✗ goto FB error: {e}")
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    log(f"  URL: {get_page_url(page)}")
    page.wait_for_timeout(5000)
    log(f"  URL sau 5s: {get_page_url(page)}")

    try:
        login_inputs = page.locator('input[placeholder="Email or phone"]').count()
        log(f"  Login form inputs: {login_inputs}")
        if login_inputs > 0:
            log("  ✗ NOT LOGGED IN")
            screenshot(page, f"session{session_id}_not_logged.png")
            browser.close()
            return 0, 0, 0, False
    except Exception as e:
        log(f"  Check login error: {e}")

    cur_url = get_page_url(page)
    if "checkpoint" in cur_url or "/login" in cur_url:
        log(f"  ✗ CHECKPOINT: {cur_url}")
        screenshot(page, f"session{session_id}_checkpoint.png")
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    log("  ✓ Login OK")

    # Open game
    log(f"[2] Open game URL...")
    log(f"  {GAME_URL[:120]}...")
    t0 = time.time()
    try:
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=45000)
        log(f"  ✓ goto game OK sau {int((time.time()-t0)*10)/10}s")
    except Exception as e:
        log(f"  ✗ goto game error: {e}")
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, True

    log(f"  URL sau goto: {get_page_url(page)}")
    log("  Đợi 20s cho game load...")
    page.wait_for_timeout(20000)
    log(f"  URL sau 20s: {get_page_url(page)}")

    log("  Dismiss popups...")
    dismiss_popups(page)
    page.wait_for_timeout(2000)
    log(f"  URL sau dismiss: {get_page_url(page)}")

    log_all_frames(page, "SAU-KHI-VAO-GAME")

    # Find game frame
    log("[2b] Tìm game frame...")
    gf = find_gf(page, max_wait=60)

    if not gf:
        log("  Frame chưa thấy, thử reload 1 lần...")
        try:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            log(f"  Reload xong, URL: {get_page_url(page)}")
            page.wait_for_timeout(25000)
            dismiss_popups(page)
            log_all_frames(page, "SAU-RELOAD")
            gf = find_gf(page, max_wait=60)
        except Exception as e:
            log(f"  Reload error: {e}")

    if not gf:
        log("  ❌ ERROR: Game frame not found sau reload")
        screenshot(page, f"session{session_id}_fail.png")
        log_all_frames(page, "FAIL")
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, True

    log("  ✓ Game loaded")

    page.wait_for_timeout(10000)

    # Wait connection
    log("[3] Wait connection object...")
    connection_ready = False
    for i in range(20):
        try:
            has_conn = gf.evaluate(
                "() => !!(window.connection && typeof connection.send === 'function')"
            )
            if has_conn:
                log(f"  ✓ connection.send OK sau {i*3}s")
                connection_ready = True
                break
            elif i % 5 == 0:
                log(f"  ⏳ Đợi connection... ({i*3}s)")
        except Exception as e:
            if i % 5 == 0:
                log(f"  ⏳ Evaluate error ({i*3}s): {str(e)[:80]}")
        time.sleep(3)

    if not connection_ready:
        log("  ⚠ connection.send chưa có — vẫn thử claim")

    if is_account_blocked(gf):
        log("  ❌ ACCOUNT BLOCKED")
        screenshot(page, f"session{session_id}_blocked.png")
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    bal_start = get_bal(gf)
    log(f"  Balance: {bal_start}")

    # Pre-claim transfer
    bal_start_num = parse_balance_num(bal_start)
    if TRANSFER_ENABLED and bal_start_num > PRE_CLAIM_TRANSFER_THRESHOLD:
        log(f"[Pre-claim] Balance {bal_start_num:,} > {PRE_CLAIM_TRANSFER_THRESHOLD:,}")
        pre = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
        if pre.get('success'):
            amt = pre.get('balance', 0)
            log(f"  ✅ Pre-claim transfer: {amt:,} xu → {TRANSFER_DEST_ID}")
            time.sleep(2)
            bal_start = get_bal(gf)
            log(f"     Balance sau: {bal_start}")
        else:
            log(f"  ❌ Pre-claim transfer fail: {pre.get('error', 'unknown')}")

    # Reward loop
    log(f"[4] Reward loop ({MAX_CYCLES} cycles)...")
    total = 0
    ok = 0
    fail = 0
    consecutive_timeouts = 0
    MAX_CONSECUTIVE_TIMEOUTS = 5
    loop_t0 = time.time()

    for i in range(MAX_CYCLES):
        if time.time() - started_at > MAX_RUNTIME:
            log("  ⏰ Hết thời gian, dừng session.")
            break

        bal_before = get_bal(gf)
        try:
            gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
        except Exception:
            pass
        time.sleep(1)

        claim_t0 = time.time()
        try:
            result = trigger_and_claim(gf)
        except Exception as e:
            log(f"  {i+1}: EXCEPTION ({str(e)[:80]})")
            fail += 1
            if fail >= 8:
                break
            time.sleep(DELAY)
            continue
        claim_elapsed = int((time.time() - claim_t0) * 10) / 10

        if result.get('success') and result.get('amount', 0) > 0:
            amount = result['amount']
            total += amount
            ok += 1
            consecutive_timeouts = 0
            time.sleep(1)
            bal_after = get_bal(gf)
            log(f"  {i+1}: +{amount} | {bal_before} -> {bal_after} | total={total} | {claim_elapsed}s")
            fail = 0
        else:
            fail += 1
            err = result.get('error', 'unknown')
            log(f"  {i+1}: FAIL ({err}) | {bal_before} | {claim_elapsed}s")

            if 'timeout' in str(err).lower():
                consecutive_timeouts += 1
                if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                    log(f"  ⚠ {consecutive_timeouts} timeouts liên tiếp — reload...")
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(20000)
                        new_gf = find_gf(page, max_wait=60)
                        if new_gf:
                            gf = new_gf
                    except Exception as e:
                        log(f"  Reload error: {e}")
                    consecutive_timeouts = 0
            else:
                consecutive_timeouts = 0

        if fail >= 8:
            log("  ⚠ Quá nhiều fail, dừng session")
            break

        if i < MAX_CYCLES - 1:
            time.sleep(DELAY)

    loop_elapsed = int(time.time() - loop_t0)
    bal_end = get_bal(gf)
    log(f"[SESSION {session_id}] Xong | ok={ok} fail={fail} | "
        f"balance {bal_start} -> {bal_end} | reward={total} | "
        f"loop_elapsed={loop_elapsed}s")

    # Final transfer
    if TRANSFER_ENABLED and total > 0:
        log(f"[SESSION {session_id}] === TRANSFER ALL → {TRANSFER_DEST_ID} ===")
        time.sleep(2)
        tr = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
        if tr.get('success'):
            amt = tr.get('balance', 0)
            log(f"  ✅ Transferred {amt:,} xu → {TRANSFER_DEST_ID}")
            time.sleep(2)
            log(f"     Balance sau: {get_bal(gf)}")
        else:
            err = tr.get('error', 'unknown')
            bal_at = tr.get('balance', 0)
            log(f"  ⚠ Transfer fail: {err} (balance was {bal_at})")

    session_elapsed = int(time.time() - session_t0)
    log(f"[SESSION {session_id}] Đóng browser (total {session_elapsed}s)...")
    try:
        browser.close()
    except Exception:
        pass

    return total, ok, fail, True


# ============================================================
# MAIN
# ============================================================
def main():
    log("=" * 60)
    log(">>> FB GAME REWARD BOT v15 — 2841623646051191 <<<")
    log("=" * 60)
    log(f"  GAME_URL={GAME_URL[:100]}...")
    log(f"  MAX_CLAIMS={MAX_CYCLES} COOLDOWN={DELAY}s")
    log(f"  MAX_RUNTIME={MAX_RUNTIME}s HEADLESS={HEADLESS}")
    log(f"  TRANSFER_ENABLED={TRANSFER_ENABLED} DEST={TRANSFER_DEST_ID}")
    log(f"  Python={sys.version.split()[0]} CWD={os.getcwd()}")

    fb_cookies = parse_cookie(COOKIE_RAW)
    if not fb_cookies:
        log("[STOP] Parse cookie thất bại.")
        return 1

    summary = cookie_summary(fb_cookies)
    log(f"[COOKIE] Summary:")
    log(f"  count={summary['count']} c_user={summary['c_user']}")
    log(f"  xs_prefix={summary['xs_prefix']} datr={summary['datr']}")
    log(f"  locale={summary['locale']} wd={summary['wd']}")

    grand_total = 0
    grand_ok = 0
    session_id = 0

    with sync_playwright() as p:
        while True:
            session_id += 1
            log("")
            log("█" * 60)
            log(f"█ RUN #{session_id}  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            log("█" * 60)

            run_started = time.time()
            try:
                total, ok, fail, cookies_ok = run_one_session(
                    p, fb_cookies, session_id, run_started
                )
            except KeyboardInterrupt:
                log("[STOP] Người dùng dừng (Ctrl+C).")
                break
            except Exception as e:
                log(f"[ERROR] session {session_id}: {e}")
                import traceback
                log(traceback.format_exc())
                total, ok, fail, cookies_ok = 0, 0, 0, False

            grand_total += total
            grand_ok += ok

            log(f"[RUN #{session_id}] Luỹ kế: {grand_ok} claim ok | {grand_total} coin")

            if not cookies_ok:
                log("[WARN] Cookie hết hạn hoặc account blocked.")

            log(f"[REST] Nghỉ {SLEEP_BETWEEN_RUNS}s rồi chạy lại...")
            time.sleep(SLEEP_BETWEEN_RUNS)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n[STOP] Người dùng dừng (Ctrl+C).")
        sys.exit(0)
