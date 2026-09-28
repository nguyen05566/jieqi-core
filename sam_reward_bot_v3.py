#!/usr/bin/env python3
"""FB Multi-Game Reward Bot v6 — FINAL.

Features:
  - Auto-loop through all FB Instant Games
  - Auto-skip games with exhausted quota (videoIndex >= 7 AND no auto-reset)
  - Mậu Binh (maubinh_xapxam) has AUTO-RESET → unlimited claims!
  - createTable(highest bet) → trigger "not enough xu" → Watch video → VIDEO_REWARD
  - When a game stops giving rewards, auto-switch to next game
  - Loops back to first game after last

Games (each has separate 7-claim quota, Mậu Binh auto-resets):
  1. maubinh_xapxam — Mậu Binh (UNLIMITED — auto-resets after 7)
  2. sam_loc_vh     — Sâm lốc (7/day, reset at 00:00)
  3. phom_tala      — Phỏm/Tá Lả (7/day, reset at 00:00)
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
    FB_COOKIES = "datr=Bu-naoV2DzYAsz945b81Jn1I; sb=Bu-nas9aEnxOeMtOfjOIAbRU; m_pixel_ratio=2; vpd=v1%3B616x360x2; c_user=61561542347462; xs=29%3ACFnA3wEH9B9D3A%3A2%3A1790554583%3A-1%3A-1; locale=en_GB; pas=100051928670915%3AdkPz2ivLwm%2C61561542347462%3AygtS8wYCm5; ps_l=1; ps_n=1; presence=C%7B%22t3%22%3A%5B%5D%2C%22utc3%22%3A1790621986752%2C%22v%22%3A1%7D; wd=360x616; fr=1ZgRRkYX1oP22NBXB.AWeDfyKNRBHTEfAa4k7CtcS-hadKGLnZAbW84CjJ0ubJnUcfUwM.Bqp-8w..Gq6.0.0.BquswZ.AWeKnaxWSJiKFHwYo1N4JAbsU_g"
    # Mậu Binh first (unlimited), then others

GAMES = [
    ("maubinh_xapxam", "https://www.facebook.com/gaming/play/maubinh_xapxam"),
    ("sam_loc_vh",     "https://www.facebook.com/gaming/play/sam_loc_vh"),
    ("phom_tala",      "https://www.facebook.com/gaming/play/phom_tala"),
]

MAX_CLAIMS = int(os.environ.get("MAX_CLAIMS", "50"))
DELAY = float(os.environ.get("DELAY", "3"))
MAX_FAILS = int(os.environ.get("MAX_FAILS", "5"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"


def get_bal(gf):
    try:
        return gf.evaluate("() => document.querySelector('.chipBalance')?.textContent.trim() || '?'")
    except:
        return "?"


def find_gf(page, max_wait=60):
    for _ in range(max_wait // 5):
        for f in page.frames:
            if "instant-bundle" in f.url:
                return f
        time.sleep(5)
    return None


def wait_ws(gf, max_wait=30):
    for _ in range(max_wait // 3):
        try:
            if gf.evaluate("() => window.connection && connection.ws && connection.ws.readyState === 1"):
                return True
        except:
            pass
        time.sleep(3)
    return False


def claim_reward(gf):
    """createTable(HIGHEST bet) → 'not enough xu' → Watch video → VIDEO_REWARD.

    Steps:
      1. Close any dialog
      2. createTable() → open bet dialog
      3. Select HIGHEST bet (last radio) → ensures balance < requirement
      4. Click 'Create table' → server checks balance
      5. If alert 'not enough xu' → click 'Watch video +N🪙'
      6. Send VIDEO_REWARD WS → claim reward
    """
    # 1. Close dialog
    try:
        gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
    except:
        pass
    time.sleep(1)

    # 2. createTable
    try:
        gf.evaluate("createTable()")
    except:
        pass
    time.sleep(2)

    # 3. Select HIGHEST bet
    try:
        gf.evaluate("""() => {
            const radios = document.querySelectorAll('input[type="radio"][name="betAmt"]');
            if (radios.length > 0) {
                const last = radios[radios.length - 1];
                last.checked = true;
                last.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }""")
    except:
        pass
    time.sleep(0.5)

    # 4. Submit
    try:
        gf.evaluate("""() => { const b = document.querySelector('input[name="CREATE"]'); if (b) b.click(); }""")
    except:
        pass
    time.sleep(3)

    # 5. Click "Watch video" if alert
    try:
        gf.evaluate("""() => {
            const ds = document.querySelectorAll('[class*="msgBox"]');
            for (const d of ds) {
                if (d.offsetParent !== null && d.textContent.includes('enough coin')) {
                    const bs = d.querySelectorAll('input[type="button"], button');
                    for (const b of bs) {
                        const v = (b.value || b.textContent || '').toLowerCase();
                        if (v.includes('watch') || v.includes('video')) { b.click(); return; }
                    }
                    // No watch button → close with OK
                    for (const b of bs) { if ((b.value||'').toLowerCase() === 'ok') { b.click(); break; } }
                }
            }
        }""")
    except:
        pass
    time.sleep(1)

    # 6. VIDEO_REWARD
    result = gf.evaluate("""() => {
        return new Promise((resolve) => {
            try {
                if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                    resolve({success: false, error: 'ws not connected'}); return;
                }
                const msg = new OutboundMessage("VIDEO_REWARD");
                msg.writeByte(1);
                let r = false;
                connection.send(msg, function(resp, ok) {
                    if (r) return; r = true;
                    if (ok) {
                        try {
                            const a = resp.readLong();
                            if (window.Ads?.RewardedVideo) {
                                window.Ads.RewardedVideo.videoIndex++;
                                if (window.Ads.RewardedVideo.updateRewardButton)
                                    window.Ads.RewardedVideo.updateRewardButton();
                            }
                            resolve({success: true, amount: a});
                        } catch(e) { resolve({success: true, amount: 0, error: e.toString()}); }
                    } else { resolve({success: false, error: 'no response'}); }
                });
                setTimeout(() => { if (!r) { r = true; resolve({success: false, error: 'timeout'}); } }, 8000);
            } catch(e) { resolve({success: false, error: e.toString()}); }
        });
    }""")
    return result


def open_game(page, game_name, game_url):
    """Open a game, return game_frame or None."""
    print(f"  Opening {game_name}...", flush=True)
    page.goto(game_url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(20000)
    gf = find_gf(page, max_wait=60)
    if not gf:
        print("  ERROR: No game frame", flush=True)
        return None
    page.wait_for_timeout(10000)
    if not wait_ws(gf):
        print("  ERROR: WS not connected", flush=True)
        return None
    print(f"  OK — WS connected, balance: {get_bal(gf)}", flush=True)
    return gf


def main():
    print("=" * 60, flush=True)
    print("FB Multi-Game Reward Bot v6 — FINAL", flush=True)
    print("=" * 60, flush=True)
    print(f"Games: {[g[0] for g in GAMES]}", flush=True)
    print(f"Max claims: {MAX_CLAIMS} | Delay: {DELAY}s | Headless: {HEADLESS}", flush=True)
    print(flush=True)

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

    grand_total = 0
    grand_claims = 0
    all_rewards = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080}, locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        )
        for c in fb_cookies:
            c['domain'] = '.facebook.com'
        context.add_cookies(fb_cookies)

        page = context.new_page()
        print("[0] Login FB...", flush=True)
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        if page.locator('input[placeholder="Email or phone"]').count() > 0:
            print("  ERROR: Not logged in", flush=True)
            browser.close()
            return 1
        print("  OK", flush=True)

        # Main loop: cycle through games
        game_idx = 0
        total_claimed = 0
        while total_claimed < MAX_CLAIMS:
            game_name, game_url = GAMES[game_idx]
            print(f"\n{'='*50}", flush=True)
            print(f"[{total_claimed+1}/{MAX_CLAIMS}] Game: {game_name}", flush=True)
            print(f"{'='*50}", flush=True)

            gf = open_game(page, game_name, game_url)
            if not gf:
                print("  Skipping — next game", flush=True)
                game_idx = (game_idx + 1) % len(GAMES)
                continue

            # Claim rewards on this game
            game_fails = 0
            game_claims = 0

            while total_claimed < MAX_CLAIMS and game_fails < MAX_FAILS:
                result = claim_reward(gf)

                if result.get('success') and result.get('amount', 0) > 0:
                    amount = result['amount']
                    grand_total += amount
                    grand_claims += 1
                    game_claims += 1
                    total_claimed += 1
                    game_fails = 0
                    all_rewards.append((game_name, amount))
                    time.sleep(1)
                    bal = get_bal(gf)
                    vi = None
                    try:
                        vi = gf.evaluate("() => window.Ads?.RewardedVideo?.videoIndex")
                    except:
                        pass
                    print(f"  +{amount} | {bal} | vi={vi} | game={game_claims} total={grand_total}", flush=True)
                else:
                    game_fails += 1
                    err = result.get('error', 'unknown')
                    print(f"  FAIL ({err}) | game_fails={game_fails}/{MAX_FAILS}", flush=True)

                    # Check videoIndex — if >= 7 and not maubinh, quota exhausted
                    try:
                        vi = gf.evaluate("() => window.Ads?.RewardedVideo?.videoIndex")
                        if vi and vi >= 7 and game_name != "maubinh_xapxam":
                            print(f"  Quota exhausted (vi={vi}), switching game", flush=True)
                            break
                    except:
                        pass

                if total_claimed < MAX_CLAIMS:
                    time.sleep(DELAY)

            print(f"\n  {game_name}: {game_claims} claims, +{sum(r for _,r in all_rewards if _==game_name)} coin", flush=True)

            if game_fails >= MAX_FAILS:
                print(f"  {MAX_FAILS} consecutive fails — switching to next game", flush=True)

            # Switch to next game
            game_idx = (game_idx + 1) % len(GAMES)

        # Grand summary
        print(flush=True)
        print("=" * 60, flush=True)
        print("GRAND SUMMARY", flush=True)
        print("=" * 60, flush=True)
        print(f"  Total claims:  {grand_claims}", flush=True)
        print(f"  Total reward:  {grand_total} coin", flush=True)
        print(f"  By game:", flush=True)
        for gname, _ in GAMES:
            game_rewards = [r for g, r in all_rewards if g == gname]
            if game_rewards:
                print(f"    {gname}: {len(game_rewards)} claims, +{sum(game_rewards)} coin", flush=True)
        print("=" * 60, flush=True)

        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
