#!/usr/bin/env python3
"""FB Sam loc reward bot v3 — simplified, GitHub Actions friendly.

No logging. More wait time. Retry game frame detection.
"""
import os, sys, time, json

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except:
    pass

from playwright.sync_api import sync_playwright

FB_COOKIES = os.environ.get("FB_COOKIES", "").strip()
GAME_URL = "https://www.facebook.com/gaming/play/sam_loc_vh"
MAX_CLAIMS = int(os.environ.get("MAX_CLAIMS", "15"))
COOLDOWN = float(os.environ.get("COOLDOWN", "3"))
MAX_FAILS = int(os.environ.get("MAX_FAILS", "8"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"


def get_balance(game_frame):
    try:
        return game_frame.evaluate("() => document.querySelector('.chipBalance')?.textContent.trim() || '?'")
    except:
        return "?"


def find_game_frame(page, max_wait=60):
    """Find game frame with retries."""
    for attempt in range(max_wait // 5):
        for f in page.frames:
            if "apps-" in f.url and "fbsbx.com" in f.url and "instant-bundle" in f.url:
                return f
        # Also try shield-bundle
        for f in page.frames:
            if "fbsbx.com" in f.url and "apps-" in f.url:
                return f
        time.sleep(5)
        print(f"  Waiting for game frame... ({(attempt+1)*5}s)", flush=True)
    return None


def claim_reward(game_frame):
    """Send VIDEO_REWARD WS. Returns {success, amount}."""
    try:
        result = game_frame.evaluate("""
            () => {
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
            }
        """)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    if not FB_COOKIES:
        print("ERROR: FB_COOKIES env var not set", flush=True)
        return 1

    print(f"Max claims: {MAX_CLAIMS} | Cooldown: {COOLDOWN}s | Headless: {HEADLESS}", flush=True)

    # Parse cookies
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

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled",
                  "--disable-gpu", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080}, locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        )
        for c in fb_cookies:
            c['domain'] = '.facebook.com'
        context.add_cookies(fb_cookies)
        page = context.new_page()

        # Step 1: Login FB
        print("[1] Login Facebook...", flush=True)
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        email_input = page.locator('input[placeholder="Email or phone"]').count()
        if email_input > 0:
            print("  ERROR: Not logged in. Check FB_COOKIES.", flush=True)
            browser.close()
            return 1
        print("  OK", flush=True)

        # Step 2: Open game
        print("[2] Open Sam loc game...", flush=True)
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=45000)
        
        # Wait for game to fully load — GitHub Actions is slower
        print("  Waiting for game to load (up to 60s)...", flush=True)
        page.wait_for_timeout(20000)  # Initial wait

        game_frame = find_game_frame(page, max_wait=60)
        if not game_frame:
            print("  ERROR: Game frame not found after 60s", flush=True)
            # Take screenshot for debugging
            page.screenshot(path="/tmp/game_load_failed.png")
            # Print all frame URLs for debugging
            print("  Frames:", flush=True)
            for f in page.frames:
                print(f"    {f.url[:150]}", flush=True)
            # Check if blocked
            body = page.inner_text('body')[:300]
            if 'blocked' in body.lower():
                print("  FB BLOCKED this account", flush=True)
            browser.close()
            return 1

        print("  Game loaded", flush=True)
        
        # Extra wait for game JS to initialize
        page.wait_for_timeout(10000)

        # Step 3: Check connection ready
        print("[3] Checking WS connection...", flush=True)
        for attempt in range(10):
            try:
                ws_ok = game_frame.evaluate("""
                    () => {
                        if (!window.connection || !connection.ws) return 'no connection';
                        return 'ready:' + connection.ws.readyState;
                    }
                """)
                if 'ready:1' in str(ws_ok):
                    print(f"  WS connected ({ws_ok})", flush=True)
                    break
                print(f"  WS not ready: {ws_ok}, retry...", flush=True)
            except:
                print(f"  Cannot check WS, retry...", flush=True)
            time.sleep(3)
        
        balance_start = get_balance(game_frame)
        print(f"  Starting balance: {balance_start}", flush=True)

        # Step 4: Claim daily reward
        print("[4] Claim daily reward...", flush=True)
        try:
            game_frame.evaluate("""
                () => {
                    try {
                        if (typeof dailyReward !== 'undefined' && dailyReward) {
                            dailyReward.show();
                            setTimeout(() => {
                                if (typeof dailyReward.claim === 'function') dailyReward.claim();
                            }, 1000);
                        }
                    } catch(e) {}
                }
            """)
            page.wait_for_timeout(3000)
            print("  Daily reward attempted", flush=True)
        except:
            print("  Daily reward failed", flush=True)

        # Step 5: Reward loop
        print(f"\n[5] Reward loop ({MAX_CLAIMS} claims, {COOLDOWN}s cooldown)...", flush=True)
        total = 0
        ok = 0
        fail = 0
        consec_fail = 0
        rewards = []

        for i in range(MAX_CLAIMS):
            # Check WS health
            try:
                ws_ok = game_frame.evaluate("() => window.connection && connection.ws && connection.ws.readyState === 1")
                if not ws_ok:
                    print(f"Claim {i+1}: WS disconnected, reloading...", flush=True)
                    page.reload(wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(20000)
                    game_frame = find_game_frame(page, max_wait=30)
                    if not game_frame:
                        print("  Game frame lost after reload, stopping", flush=True)
                        break
                    page.wait_for_timeout(5000)
            except:
                print(f"Claim {i+1}: WS check failed, skipping", flush=True)
                consec_fail += 1
                if consec_fail >= MAX_FAILS:
                    print("Too many fails, stopping", flush=True)
                    break
                time.sleep(COOLDOWN)
                continue

            bal_before = get_balance(game_frame)
            result = claim_reward(game_frame)

            if result.get('success') and result.get('amount', 0) > 0:
                amount = result['amount']
                total += amount
                ok += 1
                consec_fail = 0
                rewards.append(amount)
                time.sleep(1)
                bal_after = get_balance(game_frame)
                print(f"Claim {i+1}: +{amount} | {bal_before} -> {bal_after} | total={total}", flush=True)
            else:
                fail += 1
                consec_fail += 1
                err = result.get('error', 'unknown')
                print(f"Claim {i+1}: FAIL ({err})", flush=True)

            if consec_fail >= MAX_FAILS:
                print(f"{MAX_FAILS} consecutive fails, stopping", flush=True)
                break

            if i < MAX_CLAIMS - 1:
                time.sleep(COOLDOWN)

        # Summary
        balance_end = get_balance(game_frame)
        print(flush=True)
        print("=" * 50, flush=True)
        print(f"Claims: {ok} ok / {fail} fail / {MAX_CLAIMS} total", flush=True)
        print(f"Reward: {total} coin", flush=True)
        print(f"Balance: {balance_start} -> {balance_end}", flush=True)
        print(f"Rewards: {rewards}", flush=True)
        print("=" * 50, flush=True)

        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
