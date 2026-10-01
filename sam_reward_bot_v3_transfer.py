#!/usr/bin/env python3
"""FB Sam loc reward bot v9 — đọc cookie từ ck1.txt, ck2.txt, ck3.txt...
Chạy vòng tròn: ck1 → ck2 → ckN → ck1 → ...
Mỗi session: mở browser → login → MAX_CYCLES → close → nghỉ REST → cookie kế.
"""
import os, sys, time, glob, re

# Thử import module bổ trợ nếu có (không bắt buộc)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

GAME_URL = "https://www.facebook.com/gaming/play/sam_loc_vh"
MAX_CYCLES = int(os.environ.get("MAX_CLAIMS", "30"))
DELAY = float(os.environ.get("COOLDOWN", "3"))
REST = int(os.environ.get("REST_BETWEEN_RUNS", "3"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

# ============ ADDED: TRANSFER LOGIC ============
# Transfer xu về hub account 51977054 sau mỗi session
TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "51977054"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"


# ============================================================
# ĐỌC COOKIE TỪ FILE ck*.txt
# ============================================================
def load_all_cookie_sets(folder="."):
    """
    Quét mọi file ck*.txt, sắp xếp theo số tăng dần (ck1 < ck2 < ck10).
    Trả về: [{"file": "ck1.txt", "raw": "datr=...; sb=...; ..."}, ...]
    """
    pattern = os.path.join(folder, "ck*.txt")
    files = glob.glob(pattern)

    def sort_key(path):
        m = re.search(r'ck(\d+)\.txt$', os.path.basename(path))
        return int(m.group(1)) if m else 999999

    files.sort(key=sort_key)

    cookie_sets = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
            if not content:
                print(f"[COOKIE] {path} rỗng, bỏ qua", flush=True)
                continue
            # Chuẩn hoá: bỏ nháy, gộp xuống dòng/tab, chuẩn hoá dấu ;
            content = content.strip('"').strip("'")
            content = " ".join(content.split())
            content = content.replace(";  ", "; ").replace(" ;", ";")
            cookie_sets.append({"file": os.path.basename(path), "raw": content})
            print(f"[COOKIE] Nạp {os.path.basename(path)} "
                  f"({len(content)} ký tự)", flush=True)
        except Exception as e:
            print(f"[COOKIE] Lỗi đọc {path}: {e}", flush=True)

    return cookie_sets


def parse_cookie(raw: str):
    """Parse chuỗi cookie header thành list dict cho Playwright."""
    raw = raw.strip().strip('"').strip("'")
    raw = " ".join(raw.split())
    raw = raw.replace(";  ", "; ").replace(" ;", ";")

    # Ưu tiên dùng module bổ trợ nếu có
    if m is not None and hasattr(m, "parse_cookie_header"):
        try:
            return m.parse_cookie_header(raw)
        except Exception:
            pass

    # Fallback: http.cookies chuẩn
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
def get_bal(gf):
    try:
        return gf.evaluate(
            "() => document.querySelector('.chipBalance')?.textContent.trim() || '?'"
        )
    except Exception:
        return "?"


def transfer_all_xu(gf, dest_id=TRANSFER_DEST_ID):
    """ADDED: Transfer ALL current xu về dest_id via game's connection.send.
    
    Uses the game's OutboundMessage + connection.send (same API as VIDEO_REWARD).
    Returns dict {success, amount, status, message}.
    """
    try:
        result = gf.evaluate("""(destId) => {
            return new Promise((resolve) => {
                try {
                    // 1. Read balance from .chipBalance DOM
                    const balEl = document.querySelector('.chipBalance');
                    const balText = balEl ? balEl.textContent.trim() : '0';
                    // Parse: remove non-digit chars, handle 'k' suffix
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
                    
                    // 2. Check WS connection
                    if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                        resolve({success: false, error: 'ws not connected', balance: balance});
                        return;
                    }
                    
                    // 3. Send TRANSFER
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
                    // Timeout 12s
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


def find_gf(page, max_wait=120):
    """Find game frame. Default 120s (game takes 30-60s to load)."""
    for _ in range(max_wait // 5):
        for f in page.frames:
            if "instant-bundle" in f.url and "fbsbx.com" in f.url:
                return f
        time.sleep(5)
    return None


def trigger_and_claim(gf):
    """Y NGUYÊN mã gốc."""
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

    result = gf.evaluate("""() => {
        return new Promise((resolve) => {
            try {
                if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                    resolve({success: false, error: 'ws not connected'});
                    return;
                }
                const msg = new OutboundMessage("VIDEO_REWARD");
                msg.writeByte(1);
                let resolved = false;
                connection.send(msg, function(response, success) {
                    if (resolved) return;
                    resolved = true;
                    if (success) {
                        try {
                            const amount = response.readLong();
                            if (window.Ads && window.Ads.RewardedVideo) {
                                window.Ads.RewardedVideo.videoIndex++;
                                if (window.Ads.RewardedVideo.updateRewardButton)
                                    window.Ads.RewardedVideo.updateRewardButton();
                            }
                            resolve({success: true, amount: amount});
                        } catch(e) {
                            resolve({success: true, amount: 0, error: e.toString()});
                        }
                    } else {
                        resolve({success: false, error: 'no response'});
                    }
                });
                setTimeout(() => {
                    if (!resolved) { resolved = true; resolve({success: false, error: 'timeout'}); }
                }, 8000);
            } catch(e) {
                resolve({success: false, error: e.toString()});
            }
        });
    }""")

    if not result.get('success') or result.get('amount', 0) == 0:
        result['method'] = 'alert_clicked' if alert_clicked else 'no_alert'

    return result


# ============================================================
# SESSION
# ============================================================
def run_one_session(p, fb_cookies, session_id, started_at):
    """Mở browser → login → MAX_CYCLES → close.
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

    bal_start = get_bal(gf)
    print(f"  Balance: {bal_start}", flush=True)

    # ===== Reward loop =====
    print(f"\n[4] Reward loop ({MAX_CYCLES} cycles)...", flush=True)
    total = 0
    ok = 0
    fail = 0
    rewards = []

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
            rewards.append(amount)
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

    # ===== ADDED: Transfer all xu về hub account =====
    if TRANSFER_ENABLED:
        print(f"\n[SESSION {session_id}] === TRANSFER ALL → {TRANSFER_DEST_ID} ===", flush=True)
        try:
            # Brief delay to ensure balance DOM updated
            time.sleep(2)
            transfer_result = transfer_all_xu(gf, TRANSFER_DEST_ID)
            if transfer_result.get('success'):
                amt = transfer_result.get('balance', 0)
                msg = transfer_result.get('message', '')
                print(f"  ✅ Transferred {amt:,} xu → {TRANSFER_DEST_ID}", flush=True)
                if msg:
                    print(f"     Server: {msg[:80]}", flush=True)
                # Verify new balance
                time.sleep(2)
                bal_after_transfer = get_bal(gf)
                print(f"     Balance after transfer: {bal_after_transfer}", flush=True)
            else:
                err = transfer_result.get('error', 'unknown')
                bal_at_transfer = transfer_result.get('balance', 0)
                print(f"  ❌ Transfer fail: {err} (balance was {bal_at_transfer})", flush=True)
                msg = transfer_result.get('message', '')
                if msg:
                    print(f"     Server: {msg[:80]}", flush=True)
        except Exception as e:
            print(f"  ❌ Transfer exception: {e}", flush=True)

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
    print(f"Config: MAX_CLAIMS={MAX_CYCLES} COOLDOWN={DELAY}s REST={REST}s "
          f"MAX_RUNTIME={MAX_RUNTIME}s HEADLESS={HEADLESS}", flush=True)

    cookie_sets = load_all_cookie_sets()
    if not cookie_sets:
        print("[STOP] Không tìm thấy file ck*.txt nào trong repo.", flush=True)
        return 1

    print(f"\nTìm thấy {len(cookie_sets)} bộ cookie: "
          f"{[c['file'] for c in cookie_sets]}", flush=True)

    started_at = time.time()
    grand_total = 0
    grand_ok = 0
    session_id = 0
    cookie_idx = 0

    with sync_playwright() as p:
        while True:
            if time.time() - started_at > MAX_RUNTIME:
                print(f"\n[TIME UP] Đã chạy {int(time.time()-started_at)}s, thoát.",
                      flush=True)
                break

            entry = cookie_sets[cookie_idx % len(cookie_sets)]
            round_no = cookie_idx // len(cookie_sets) + 1
            cookie_idx += 1

            print(f"\n{'='*60}", flush=True)
            print(f">>> COOKIE: {entry['file']}  |  vòng {round_no}  "
                  f"|  lượt #{cookie_idx}", flush=True)
            print(f"{'='*60}", flush=True)

            fb_cookies = parse_cookie(entry["raw"])
            if not fb_cookies:
                print(f"[WARN] {entry['file']} parse rỗng, bỏ qua.", flush=True)
                continue

            session_id += 1
            try:
                total, ok, fail, cookies_ok = run_one_session(
                    p, fb_cookies, session_id, started_at
                )
            except Exception as e:
                print(f"[ERROR] session {session_id}: {e}", flush=True)
                total, ok, fail, cookies_ok = 0, 0, 0, False

            grand_total += total
            grand_ok += ok

            if not cookies_ok:
                print(f"[WARN] Cookie {entry['file']} hết hạn — bỏ qua, "
                      f"chuyển cookie kế tiếp.", flush=True)
                continue

            if time.time() - started_at > MAX_RUNTIME:
                break

            # Hết 1 vòng cookie?
            if cookie_idx % len(cookie_sets) == 0:
                print(f"[CYCLE] Đã xong vòng {round_no} với "
                      f"{len(cookie_sets)} cookie. Nghỉ {REST}s rồi lặp lại...",
                      flush=True)
                time.sleep(REST)
            else:
                next_file = cookie_sets[cookie_idx % len(cookie_sets)]['file']
                print(f"[REST] Nghỉ {REST}s rồi sang {next_file}...", flush=True)
                time.sleep(REST)

        print("\n" + "=" * 60, flush=True)
        print(f"  TỔNG: {session_id} sessions | {grand_ok} claim ok | "
              f"{grand_total} coin", flush=True)
        print(f"  Thời gian: {int(time.time()-started_at)}s", flush=True)
        print("=" * 60, flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
