#!/usr/bin/env python3
"""FB Sam loc reward bot v8 — y như bản gốc, thêm vòng lặp:
mở browser → login → 30 cycles → close → nghỉ 60s → lặp lại.
Cookie KHÔNG bị xoá, dùng lại nguyên vẹn.
"""
import os, sys, time

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except:
    pass

from playwright.sync_api import sync_playwright

FB_COOKIES = os.environ.get("FB_COOKIES", "").strip()
if not FB_COOKIES:
    FB_COOKIES = "datr=Bu-naoV2DzYAsz945b81Jn1I; sb=Bu-nas9aEnxOeMtOfjOIAbRU; m_pixel_ratio=2; vpd=v1%3B616x360x2; c_user=61561542347462; xs=29%3ACFnA3wEH9B9D3A%3A2%3A1790554583%3A-1%3A-1; locale=en_GB; pas=100051928670915%3AdkPz2ivLwm%2C61561542347462%3AygtS8wYCm5; ps_l=1; ps_n=1; presence=C%7B%22t3%22%3A%5B%5D%2C%22utc3%22%3A1790621986752%2C%22v%22%3A1%7D; wd=360x616; fr=1ZgRRkYX1oP22NBXB.AWdhqJijw632suL5gyEWH6zdQJk2-HKqUlmlD2hniOm6xTA9ops.Bqp-8w..AAA.0.0.Bqurso.AWf_e7mTQsdpD5QFmU18288z6oM; fbl_st=101731726%3BT%3A29843708; wl_cbv=v2%3Bclient_version%3A3306%3Btimestamp%3A1790622504"

GAME_URL = "https://www.facebook.com/gaming/play/sam_loc_vh"
MAX_CYCLES = int(os.environ.get("MAX_CLAIMS", "30"))
DELAY = float(os.environ.get("COOLDOWN", "3"))
REST = int(os.environ.get("REST_BETWEEN_RUNS", "60"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"


def get_bal(gf):
    try:
        return gf.evaluate("() => document.querySelector('.chipBalance')?.textContent.trim() || '?'")
    except:
        return "?"


def find_gf(page, max_wait=60):
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
    except: pass
    time.sleep(2)

    try:
        gf.evaluate("""() => {
            const r = document.getElementById('radio_11');
            if (r) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }
        }""")
    except: pass
    time.sleep(0.5)

    try:
        gf.evaluate("""() => {
            const b = document.querySelector('input[name="CREATE"]');
            if (b) b.click();
        }""")
    except: pass
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
    except: pass

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


def run_one_session(p, fb_cookies, session_id, started_at):
    """Mở browser mới → login → chạy MAX_CYCLES → close. Trả (total, ok, fail, cookies_still_ok)."""
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
    for c in fb_cookies:
        c['domain'] = '.facebook.com'
    context.add_cookies(fb_cookies)
    page = context.new_page()

    # ===== Y NGUYÊN mã gốc =====
    print("[1] Login FB...", flush=True)
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    if page.locator('input[placeholder="Email or phone"]').count() > 0:
        print("  ERROR: Not logged in", flush=True)
        browser.close()
        return 0, 0, 0, False
    print("  OK", flush=True)

    print("[2] Open game...", flush=True)
    page.goto(GAME_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(20000)
    gf = find_gf(page, max_wait=60)
    if not gf:
        print("  ERROR: Game frame not found", flush=True)
        browser.close()
        return 0, 0, 0, True
    print("  Game loaded", flush=True)
    page.wait_for_timeout(10000)

    print("[3] Wait WS...", flush=True)
    for _ in range(10):
        try:
            if gf.evaluate("() => window.connection && connection.ws && connection.ws.readyState === 1"):
                print("  WS connected", flush=True)
                break
        except: pass
        time.sleep(3)

    bal_start = get_bal(gf)
    print(f"  Balance: {bal_start}", flush=True)

    # ===== Vòng claim — y nguyên mã gốc =====
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
        except: pass
        time.sleep(1)

        result = trigger_and_claim(gf)

        if result.get('success') and result.get('amount', 0) > 0:
            amount = result['amount']
            total += amount
            ok += 1
            rewards.append(amount)
            time.sleep(1)
            bal_after = get_bal(gf)
            print(f"  {i+1}: +{amount} | {bal_before} -> {bal_after} | total={total}", flush=True)
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
    print(f"[SESSION {session_id}] Xong | ok={ok} fail={fail} | balance {bal_start} -> {bal_end} | reward={total}",
          flush=True)

    # ===== ĐÓNG BROWSER — KHÔNG xoá cookie =====
    print(f"[SESSION {session_id}] Đóng browser (giữ cookie)...", flush=True)
    try:
        browser.close()
    except: pass

    return total, ok, fail, True


def main():
    print(f"Config: MAX_CLAIMS={MAX_CYCLES} COOLDOWN={DELAY}s REST={REST}s "
          f"MAX_RUNTIME={MAX_RUNTIME}s HEADLESS={HEADLESS}", flush=True)

    try:
        fb_cookies = m.parse_cookie_header(FB_COOKIES)
    except:
        import http.cookies
        parsed = http.cookies.SimpleCookie()
        parsed.load(FB_COOKIES)
        fb_cookies = [
            {"name": n, "value": mv.value, "domain": ".facebook.com",
             "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
            for n, mv in parsed.items() if n and mv.value
        ]

    started_at = time.time()
    grand_total = 0
    grand_ok = 0
    session_id = 0

    with sync_playwright() as p:
        while True:
            if time.time() - started_at > MAX_RUNTIME:
                print(f"\n[TIME UP] Đã chạy {int(time.time()-started_at)}s, thoát.", flush=True)
                break

            session_id += 1
            total, ok, fail, cookies_ok = run_one_session(p, fb_cookies, session_id, started_at)
            grand_total += total
            grand_ok += ok

            # Cookie hỏng → dừng job
            if not cookies_ok:
                print("[STOP] Cookie hết hạn — cần update FB_COOKIES secret.", flush=True)
                break

            # Nghỉ 60s rồi session mới
            if time.time() - started_at > MAX_RUNTIME:
                break
            print(f"[REST] Nghỉ {REST}s rồi mở session {session_id+1}...", flush=True)
            time.sleep(REST)

        print("\n" + "=" * 60, flush=True)
        print(f"  TỔNG: {session_id} sessions | {grand_ok} claim ok | {grand_total} coin", flush=True)
        print(f"  Thời gian: {int(time.time()-started_at)}s", flush=True)
        print("=" * 60, flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
