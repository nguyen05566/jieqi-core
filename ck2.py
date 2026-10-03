#!/usr/bin/env python3
"""FB Sam loc reward bot v11 — GỘP tất cả: bot + transfer + run_forever.
CHỈ ĐỌC 1 FILE COOKIE CỐ ĐỊNH (mặc định ck1.txt, đổi qua env COOKIE_FILE).
Vòng lặp vô hạn tích hợp trong Python — không cần file .sh.

Mỗi run: mở browser → login → MAX_CYCLES claim → transfer hết xu → close → nghỉ → lặp.
"""
import os, sys, time

# Thử import module bổ trợ nếu có (không bắt buộc)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

# ============================================================
# CONFIG (đọc từ biến môi trường)
# ============================================================
GAME_URL = "https://www.facebook.com/gaming/play/sam_loc_vh"
MAX_CYCLES = int(os.environ.get("MAX_CLAIMS", "40"))
DELAY = float(os.environ.get("COOLDOWN", "3"))
REST = int(os.environ.get("REST_BETWEEN_RUNS", "5"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", "600"))  # mỗi run (giây)
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

# >>> CHỈ ĐỌC 1 FILE COOKIE CỐ ĐỊNH <<<
COOKIE_FILE = os.environ.get("COOKIE_FILE", "ck1.txt")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(SCRIPT_DIR, COOKIE_FILE)

# Nghỉ giữa các run vô hạn
SLEEP_BETWEEN_RUNS = int(os.environ.get("SLEEP_BETWEEN_RUNS", "10"))

# Transfer
TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "51977054"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"
PRE_CLAIM_TRANSFER_THRESHOLD = int(
    os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000")
)


# ============================================================
# ĐỌC COOKIE TỪ 1 FILE CỐ ĐỊNH
# ============================================================
def load_cookie_set(path=COOKIE_PATH):
    """Đọc duy nhất 1 file cookie. Trả về chuỗi raw hoặc None."""
    if not os.path.exists(path):
        print(f"[COOKIE] Không tìm thấy file: {path}", flush=True)
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
        if not content:
            print(f"[COOKIE] {path} rỗng.", flush=True)
            return None
        content = content.strip('"').strip("'")
        content = " ".join(content.split())
        content = content.replace(";  ", "; ").replace(" ;", ";")
        print(f"[COOKIE] Nạp {os.path.basename(path)} "
              f"({len(content)} ký tự)", flush=True)
        return content
    except Exception as e:
        print(f"[COOKIE] Lỗi đọc {path}: {e}", flush=True)
        return None


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
# HELPER
# ============================================================
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


def get_bal(gf):
    try:
        return gf.evaluate(
            "() => document.querySelector('.chipBalance')?.textContent.trim() || '?'"
        )
    except Exception:
        return "?"


def find_gf(page, max_wait=120):
    """Find game frame. Default 120s."""
    for _ in range(max_wait // 5):
        for f in page.frames:
            if "instant-bundle" in f.url and "fbsbx.com" in f.url:
                return f
        time.sleep(5)
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


def ensure_ws_connected(gf, page, max_retries=2):
    """Check WS state, reload page if disconnected. True nếu WS OK."""
    try:
        ws_ok = gf.evaluate(
            "() => !!(window.connection && connection.ws && connection.ws.readyState === 1)"
        )
        if ws_ok:
            return True
    except Exception:
        pass

    print(f"  ⚠ WS not connected — reloading page...", flush=True)

    for retry in range(max_retries):
        try:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(20000)

            new_gf = find_gf(page, max_wait=60)
            if not new_gf:
                print(f"  ⚠ Reload #{retry+1}: game frame not found", flush=True)
                continue

            for _ in range(15):  # ~45s
                try:
                    ws_ok = new_gf.evaluate(
                        "() => !!(window.connection && connection.ws && connection.ws.readyState === 1)"
                    )
                    if ws_ok:
                        print(f"  ✓ WS reconnected after reload #{retry+1}",
                              flush=True)
                        return True
                except Exception:
                    pass
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  ⚠ Reload #{retry+1} error: {e}", flush=True)

    print(f"  ❌ WS reconnect failed after {max_retries} reloads", flush=True)
    return False


def transfer_all_xu(gf, page, dest_id=TRANSFER_DEST_ID):
    """Transfer ALL current xu về dest_id via game's connection.send."""
    if not ensure_ws_connected(gf, page):
        return {"success": False, "error": "ws reconnect failed after reloads"}

    gf_new = find_gf(page, max_wait=30)
    if gf_new:
        gf = gf_new

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


def trigger_and_claim(gf, page):
    """Claim với retry 1 lần + WS reconnect trước mỗi claim."""
    if not ensure_ws_connected(gf, page, max_retries=1):
        return {"success": False, "error": "ws reconnect failed"}
    gf_new = find_gf(page, max_wait=30)
    if gf_new:
        gf = gf_new

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

        if result.get('success') and result.get('amount', 0) > 0:
            break

        if attempt < max_attempts - 1:
            err = result.get('error', 'unknown')
            print(f"  attempt {attempt+1}/{max_attempts}: FAIL ({err}), retrying...",
                  flush=True)
            try:
                gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
            except Exception:
                pass
            time.sleep(2)
            if not ensure_ws_connected(gf, page, max_retries=1):
                print(f"  WS still dead, skip retry", flush=True)
                break
            gf_new = find_gf(page, max_wait=30)
            if gf_new:
                gf = gf_new
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
        else:
            err = result.get('error', 'unknown')
            print(f"  attempt {attempt+1}/{max_attempts}: FAIL ({err}) — giving up",
                  flush=True)

    if not result.get('success') or result.get('amount', 0) == 0:
        result['method'] = 'alert_clicked' if alert_clicked else 'no_alert'

    return result


# ============================================================
# SESSION
# ============================================================
def run_one_session(p, fb_cookies, session_id, started_at):
    """Mở browser → login → claim → transfer → close.
    Trả về (total, ok, fail, cookies_ok)."""
    print(f"\n########## SESSION {session_id} ##########", flush=True)

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
    print("  OK", flush=True)

    # ===== Open game =====
    print("[2] Open game...", flush=True)
    try:
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(f"  ERROR goto game: {e}", flush=True)
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, True

    page.wait_for_timeout(20000)
    gf = find_gf(page, max_wait=60)
    if not gf:
        print("  ERROR: Game frame not found", flush=True)
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, True
    print("  Game loaded", flush=True)
    page.wait_for_timeout(10000)

    # ===== Wait WS =====
    print("[3] Wait WS...", flush=True)
    for _ in range(10):
        try:
            if gf.evaluate(
                "() => window.connection && connection.ws && connection.ws.readyState === 1"
            ):
                print("  WS connected", flush=True)
                break
        except Exception:
            pass
        time.sleep(3)

    # ===== Check blocked =====
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
        try:
            pre = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
            if pre.get('success'):
                amt = pre.get('balance', 0)
                print(f"  ✅ Pre-claim transfer: {amt:,} xu → {TRANSFER_DEST_ID}",
                      flush=True)
                time.sleep(2)
                bal_start = get_bal(gf)
                print(f"     Balance sau pre-transfer: {bal_start}", flush=True)
            else:
                print(f"  ❌ Pre-claim transfer fail: "
                      f"{pre.get('error', 'unknown')}", flush=True)
        except Exception as e:
            print(f"  ❌ Pre-claim transfer exception: {e}", flush=True)
    elif bal_start_num > 0:
        print(f"  (Balance {bal_start_num:,} ≤ "
              f"{PRE_CLAIM_TRANSFER_THRESHOLD:,}, skip pre-claim)", flush=True)

    # ===== Reward loop =====
    print(f"\n[4] Reward loop ({MAX_CYCLES} cycles)...", flush=True)
    total = 0
    ok = 0
    fail = 0

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
            result = trigger_and_claim(gf, page)
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
            time.sleep(1)
            bal_after = get_bal(gf)
            print(f"  {i+1}: +{amount} | {bal_before} -> {bal_after} | total={total}",
                  flush=True)
            fail = 0
        else:
            fail += 1
            err = result.get('error', 'unknown')
            print(f"  {i+1}: FAIL ({err}) | {bal_before}", flush=True)

        if fail >= 8:
            print("  Too many fails, stopping session", flush=True)
            break

        if i < MAX_CYCLES - 1:
            time.sleep(DELAY)

    bal_end = get_bal(gf)
    print(f"[SESSION {session_id}] Xong | ok={ok} fail={fail} | "
          f"balance {bal_start} -> {bal_end} | reward={total}", flush=True)

    # ===== Transfer cuối session =====
    if TRANSFER_ENABLED:
        print(f"\n[SESSION {session_id}] === TRANSFER ALL → "
              f"{TRANSFER_DEST_ID} ===", flush=True)
        try:
            time.sleep(2)
            tr = transfer_all_xu(gf, page, TRANSFER_DEST_ID)
            if tr.get('success'):
                amt = tr.get('balance', 0)
                print(f"  ✅ Transferred {amt:,} xu → {TRANSFER_DEST_ID}", flush=True)
                time.sleep(2)
                print(f"     Balance sau transfer: {get_bal(gf)}", flush=True)
            else:
                print(f"  ❌ Transfer fail: {tr.get('error', 'unknown')} "
                      f"(balance was {tr.get('balance', 0)})", flush=True)
        except Exception as e:
            print(f"  ❌ Transfer exception: {e}", flush=True)

    print(f"[SESSION {session_id}] Đóng browser (giữ cookie)...", flush=True)
    try:
        browser.close()
    except Exception:
        pass

    return total, ok, fail, True


# ============================================================
# MAIN — VÒNG LẶP VÔ HẠN
# ============================================================
def main():
    print(f"Config: COOKIE_FILE={COOKIE_FILE} MAX_CLAIMS={MAX_CYCLES} "
          f"COOLDOWN={DELAY}s MAX_RUNTIME={MAX_RUNTIME}s "
          f"HEADLESS={HEADLESS} SLEEP_BETWEEN_RUNS={SLEEP_BETWEEN_RUNS}s "
          f"TRANSFER_ENABLED={TRANSFER_ENABLED} DEST={TRANSFER_DEST_ID}",
          flush=True)
    print(f"Cookie path: {COOKIE_PATH}", flush=True)

    if not os.path.exists(COOKIE_PATH):
        print(f"[STOP] Không tìm thấy file cookie: {COOKIE_PATH}", flush=True)
        return 1

    grand_total = 0
    grand_ok = 0
    session_id = 0

    with sync_playwright() as p:
        while True:  # VÒNG LẶP VÔ HẠN
            raw = load_cookie_set(COOKIE_PATH)
            if not raw:
                print(f"[WARN] Cookie rỗng/không đọc được, nghỉ "
                      f"{SLEEP_BETWEEN_RUNS}s rồi thử lại...", flush=True)
                time.sleep(SLEEP_BETWEEN_RUNS)
                continue

            fb_cookies = parse_cookie(raw)
            if not fb_cookies:
                print("[WARN] Parse cookie rỗng, nghỉ rồi thử lại...", flush=True)
                time.sleep(SLEEP_BETWEEN_RUNS)
                continue

            session_id += 1
            print(f"\n{'='*60}", flush=True)
            print(f">>> RUN #{session_id}  |  cookie: {COOKIE_FILE}  "
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
                print("[WARN] Cookie hết hạn hoặc account blocked — cần "
                      f"cập nhật {COOKIE_FILE}.", flush=True)

            print(f"[REST] Nghỉ {SLEEP_BETWEEN_RUNS}s rồi chạy lại...",
                  flush=True)
            time.sleep(SLEEP_BETWEEN_RUNS)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[STOP] Người dùng dừng (Ctrl+C).", flush=True)
        sys.exit(0)
