#!/usr/bin/env python3
"""FB Sam loc reward bot v13b — URL fb.gg + cookie mới (c_user=61562610920837).
BỎ check WS. Chỉ reload khi timeout liên tiếp >= 5.
"""
import os, sys, time

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

# ============================================================
# >>> COOKIE MỚI <<<
# ============================================================
COOKIE_RAW = (
    "sb=XSa_ahbAv9XMUHfep4z2jQUb; m_pixel_ratio=2; vpd=v1%3B616x360x2; "
    "ps_l=1; ps_n=1; locale=vi_VN; "
    "pas=61595197311852%3APOwi1i3tVJ%2C61594782729357%3AVvbK8iGoqB%2C"
    "61594960651753%3Aci75sCyaff%2C61594746041618%3AiAAzWgyfvh%2C"
    "100051928670915%3Aw80kSunsKe%2C61561542347462%3AMdbf81FzjV%2C"
    "61562610920837%3A83znIlEigO; "
    "wl_cbv=v2%3Bclient_version%3A3310%3Btimestamp%3A1791022744; "
    "datr=wdjAau4MNR7IM08V5XLbosEH; "
    "c_user=61562610920837; "
    "xs=28%3ANrZsCxInw1jA6Q%3A2%3A1791023450%3A-1%3A-1; "
    "fr=0ZX5mgCABu4MTVFSz.AWcuhEX2bUUNxjweBtzGxg3dt_xwbsb-gRxPf8bHOn62MNo6GuE"
    ".BqvyZd..GrA.0.0.BqwNlt.AWegPj-OCsq4jU5OyUwbGaoJ9oo; "
    "wd=360x616"
)

# ============================================================
# >>> URL GAME MỚI <<<
# ============================================================
GAME_URL = "https://fb.gg/play/sam_loc_vh"

# URL phụ để fallback nếu fb.gg không load
GAME_URL_FALLBACK = "https://www.facebook.com/gaming/play/sam_loc_vh"

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


def find_gf(page, max_wait=120):
    """Tìm iframe game — hỗ trợ cả instant-bundle (fbsbx) và fb.gg."""
    for _ in range(max_wait // 5):
        for f in page.frames:
            url = f.url
            if "instant-bundle" in url and "fbsbx.com" in url:
                return f
            # Một số game fb.gg dùng URL khác
            if "fb.gg" in url and "sam_loc" in url and f != page.main_frame:
                return f
            if "gaming" in url and "sam_loc" in url and f != page.main_frame:
                return f
        time.sleep(5)
    return None


def debug_frames(page, tag=""):
    """Log tất cả frame URL — dùng khi không tìm thấy game frame."""
    print(f"  [DEBUG{(' '+tag) if tag else ''}] Frames hiện có:", flush=True)
    for i, f in enumerate(page.frames):
        print(f"    [{i}] {f.url[:150]}", flush=True)
    try:
        page.screenshot(path="debug_fail.png", full_page=False)
        print("  [DEBUG] Screenshot: debug_fail.png", flush=True)
    except Exception:
        pass


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
    """Đóng các dialog FB (đồng ý điều khoản, xác nhận, cookie banner...)."""
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
        print(f"  Đã đóng {clicked} popup/button", flush=True)


def reload_game_page(page):
    print("  ⟳ Reload page (send timed out)...", flush=True)
    try:
        page.reload(wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(20000)
        new_gf = find_gf(page, max_wait=60)
        if new_gf:
            print("  ✓ Game reloaded", flush=True)
            page.wait_for_timeout(10000)
            return new_gf
        print("  ✗ Game frame not found after reload", flush=True)
        return None
    except Exception as e:
        print(f"  ✗ Reload error: {e}", flush=True)
        return None


# ============================================================
# TRANSFER
# ============================================================
def transfer_all_xu(gf, page, dest_id=TRANSFER_DEST_ID):
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
        return result
    except Exception as e:
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
            print(f"    attempt {attempt+1}/{max_attempts}: FAIL ({err}), retrying...",
                  flush=True)
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
    print(f"\n########## SESSION {session_id} ##########", flush=True)

    browser = p.chromium.launch(
        headless=HEADLESS,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080}, locale="vi-VN",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/139.0.0.0 Safari/537.36",
    )

    try:
        for c in fb_cookies:
            c['domain'] = '.facebook.com'
        context.add_cookies(fb_cookies)
    except Exception as e:
        print(f"  ERROR add_cookies: {e}", flush=True)
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    page = context.new_page()

    # ===== Login check =====
    print("[1] Login FB...", flush=True)
    try:
        page.goto("https://www.facebook.com/",
                  wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  ERROR goto FB: {e}", flush=True)
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    page.wait_for_timeout(5000)

    try:
        if page.locator('input[placeholder="Email or phone"]').count() > 0:
            print("  ERROR: Not logged in (cookie hết hạn?)", flush=True)
            browser.close()
            return 0, 0, 0, False
    except Exception:
        pass

    # Checkpoint check
    cur_url = page.url
    if "checkpoint" in cur_url or "/login" in cur_url:
        print(f"  ❌ FB CHECKPOINT: {cur_url}", flush=True)
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    print("  OK", flush=True)

    # ===== Open game (fb.gg) =====
    print(f"[2] Open game: {GAME_URL}", flush=True)
    gf = None
    for attempt_url in [GAME_URL, GAME_URL_FALLBACK]:
        try:
            page.goto(attempt_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"  ERROR goto {attempt_url}: {e}", flush=True)
            continue

        page.wait_for_timeout(20000)
        dismiss_popups(page)     # đóng đồng ý điều khoản / cookie banner
        page.wait_for_timeout(2000)

        gf = find_gf(page, max_wait=60)
        if gf:
            print(f"  Game loaded từ {attempt_url}", flush=True)
            break
        else:
            print(f"  Không tìm thấy frame từ {attempt_url}, thử URL kia...",
                  flush=True)

    if not gf:
        print("  ❌ ERROR: Game frame not found (đã thử cả 2 URL)", flush=True)
        debug_frames(page, "fail")
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, True

    page.wait_for_timeout(10000)

    # ===== Wait connection =====
    print("[3] Wait connection object...", flush=True)
    connection_ready = False
    for _ in range(20):
        try:
            has_conn = gf.evaluate(
                "() => !!(window.connection && typeof connection.send === 'function')"
            )
            if has_conn:
                print("  connection.send available", flush=True)
                connection_ready = True
                break
        except Exception:
            pass
        time.sleep(3)
    if not connection_ready:
        print("  ⚠ connection.send không xuất hiện — vẫn thử claim", flush=True)

    # ===== Blocked check =====
    if is_account_blocked(gf):
        print(f"  ❌ ACCOUNT BLOCKED — bỏ qua run này.", flush=True)
        try:
            gf.evaluate("""() => {
                const btns = document.querySelectorAll('input[type="button"], button');
                for (const b of btns) {
                    const t = (b.value || b.textContent || '').toLowerCase().trim();
                    if (t === 'ok' || t === 'đóng' || t === 'close') b.click();
                }
            }""")
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    bal_start = get_bal(gf)
    print(f"  Balance: {bal_start}", flush=True)

    # ===== Pre-claim transfer =====
    bal_start_num = parse_balance_num(bal_start)
    if TRANSFER_ENABLED and bal_start_num > PRE_CLAIM_TRANSFER_THRESHOLD:
        print(f"\n[Pre-claim] Balance {bal_start_num:,} > "
              f"{PRE_CLAIM_TRANSFER_THRESHOLD:,}, transfer trước...", flush=True)
        pre = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
        if pre.get('success'):
            amt = pre.get('balance', 0)
            print(f"  ✅ Pre-claim transfer: {amt:,} xu → {TRANSFER_DEST_ID}",
                  flush=True)
            time.sleep(2)
            bal_start = get_bal(gf)
            print(f"     Balance sau pre-transfer: {bal_start}", flush=True)
        else:
            print(f"  ❌ Pre-claim transfer fail: {pre.get('error', 'unknown')}",
                  flush=True)
    elif bal_start_num > 0:
        print(f"  (Balance {bal_start_num:,} ≤ "
              f"{PRE_CLAIM_TRANSFER_THRESHOLD:,}, skip pre-claim)", flush=True)

    # ===== Reward loop =====
    print(f"\n[4] Reward loop ({MAX_CYCLES} cycles)...", flush=True)
    total = 0
    ok = 0
    fail = 0
    consecutive_timeouts = 0
    MAX_CONSECUTIVE_TIMEOUTS = 5

    for i in range(MAX_CYCLES):
        if time.time() - started_at > MAX_RUNTIME:
            print("  Hết thời gian cho phép, dừng session.", flush=True)
            break

        bal_before = get_bal(gf)
        try:
            gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
        except Exception:
            pass
        time.sleep(1)

        try:
            result = trigger_and_claim(gf)
        except Exception as e:
            print(f"  {i+1}: EXCEPTION ({e})", flush=True)
            fail += 1
            if fail >= 8:
                break
            time.sleep(DELAY)
            continue

        if result.get('success') and result.get('amount', 0) > 0:
            amount = result['amount']
            total += amount
            ok += 1
            consecutive_timeouts = 0
            time.sleep(1)
            bal_after = get_bal(gf)
            print(f"  {i+1}: +{amount} | {bal_before} -> {bal_after} | total={total}",
                  flush=True)
            fail = 0
        else:
            fail += 1
            err = result.get('error', 'unknown')
            print(f"  {i+1}: FAIL ({err}) | {bal_before}", flush=True)

            if 'timeout' in str(err).lower():
                consecutive_timeouts += 1
                if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                    print(f"  ⚠ {consecutive_timeouts} timeouts liên tiếp — reload page...",
                          flush=True)
                    new_gf = reload_game_page(page)
                    if new_gf:
                        gf = new_gf
                    consecutive_timeouts = 0
            else:
                consecutive_timeouts = 0

        if fail >= 8:
            print("  Too many fails, stopping session", flush=True)
            break

        if i < MAX_CYCLES - 1:
            time.sleep(DELAY)

    bal_end = get_bal(gf)
    print(f"[SESSION {session_id}] Xong | ok={ok} fail={fail} | "
          f"balance {bal_start} -> {bal_end} | reward={total}", flush=True)

    # ===== Transfer cuối session =====
    if TRANSFER_ENABLED and total > 0:
        print(f"\n[SESSION {session_id}] === TRANSFER ALL → "
              f"{TRANSFER_DEST_ID} ===", flush=True)
        time.sleep(2)
        tr = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
        if tr.get('success'):
            amt = tr.get('balance', 0)
            print(f"  ✅ Transferred {amt:,} xu → {TRANSFER_DEST_ID}", flush=True)
            time.sleep(2)
            print(f"     Balance sau transfer: {get_bal(gf)}", flush=True)
        else:
            err = tr.get('error', 'unknown')
            bal_at = tr.get('balance', 0)
            print(f"  ⚠ Transfer fail: {err} (balance was {bal_at})", flush=True)
            print(f"     → Sẽ transfer ở session sau (pre-claim)", flush=True)

    print(f"[SESSION {session_id}] Đóng browser (giữ cookie)...", flush=True)
    try:
        browser.close()
    except Exception:
        pass

    return total, ok, fail, True


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"Config: COOKIE c_user=61562610920837 | GAME_URL={GAME_URL} "
          f"MAX_CLAIMS={MAX_CYCLES} COOLDOWN={DELAY}s "
          f"MAX_RUNTIME={MAX_RUNTIME}s HEADLESS={HEADLESS} "
          f"SLEEP_BETWEEN_RUNS={SLEEP_BETWEEN_RUNS}s "
          f"TRANSFER_ENABLED={TRANSFER_ENABLED} DEST={TRANSFER_DEST_ID}",
          flush=True)
    print(f"Mode: NO WS CHECK — reload only after 5 consecutive timeouts",
          flush=True)

    fb_cookies = parse_cookie(COOKIE_RAW)
    if not fb_cookies:
        print("[STOP] Parse cookie thất bại.", flush=True)
        return 1
    print(f"[COOKIE] Parse {len(fb_cookies)} cookie OK.", flush=True)

    grand_total = 0
    grand_ok = 0
    session_id = 0

    with sync_playwright() as p:
        while True:
            session_id += 1
            print(f"\n{'='*60}", flush=True)
            print(f">>> RUN #{session_id}  |  c_user=61562610920837  "
                  f"|  {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
            print(f"{'='*60}", flush=True)

            run_started = time.time()
            try:
                total, ok, fail, cookies_ok = run_one_session(
                    p, fb_cookies, session_id, run_started
                )
            except Exception as e:
                print(f"[ERROR] session {session_id}: {e}", flush=True)
                total, ok, fail, cookies_ok = 0, 0, 0, False

            grand_total += total
            grand_ok += ok

            print(f"[RUN #{session_id}] Luỹ kế: {grand_ok} claim ok | "
                  f"{grand_total} coin", flush=True)

            if not cookies_ok:
                print("[WARN] Cookie hết hạn hoặc account blocked.", flush=True)

            print(f"[REST] Nghỉ {SLEEP_BETWEEN_RUNS}s rồi chạy lại...",
                  flush=True)
            time.sleep(SLEEP_BETWEEN_RUNS)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[STOP] Người dùng dừng (Ctrl+C).", flush=True)
        sys.exit(0)
