#!/usr/bin/env python3
"""FB Sam loc reward bot v2 — auto-retry + daily reward + logging.

Features:
  - Loop claim VIDEO_REWARD continuously until max attempts or no reward
  - Auto-retry on cooldown (configurable delay)
  - Claim daily reward in parallel (dailyReward.show())
  - Save log + balance history to JSON file
  - Configurable via environment variables

Usage:
    python3 sam_reward_bot_v2.py
    
    # Custom settings
    MAX_CLAIMS=50 COOLDOWN=3 HEADLESS=true python3 sam_reward_bot_v2.py
"""
import os, sys, time, json, re
from pathlib import Path
from datetime import datetime

try:
    sys.path.insert(0, str(Path(__file__).parent / "download"))
    import board_dom_merged as m
except:
    pass

from playwright.sync_api import sync_playwright

# ============================================================
# CONFIG
# ============================================================
FB_COOKIES = os.environ.get("FB_COOKIES", """
datr=Bu-naoV2DzYAsz945b81Jn1I; sb=Bu-nas9aEnxOeMtOfjOIAbRU; m_pixel_ratio=2; vpd=v1%3B616x360x2; c_user=61561542347462; xs=29%3ACFnA3wEH9B9D3A%3A2%3A1790554583%3A-1%3A-1; locale=en_GB; pas=100051928670915%3AdkPz2ivLwm%2C61561542347462%3AygtS8wYCm5; ps_l=1; ps_n=1; presence=C%7B%22t3%22%3A%5B%5D%2C%22utc3%22%3A1790621986752%2C%22v%22%3A1%7D; wd=360x616; fr=1ZgRRkYX1oP22NBXB.AWdhqJijw632suL5gyEWH6zdQJk2-HKqUlmlD2hniOm6xTA9ops.Bqp-8w..AAA.0.0.Bqurso.AWf_e7mTQsdpD5QFmU18288z6oM; fbl_st=101731726%3BT%3A29843708; wl_cbv=v2%3Bclient_version%3A3306%3Btimestamp%3A1790622504
""").strip()

GAME_URL = "https://www.facebook.com/gaming/play/sam_loc_vh"

# Max reward claims to attempt (0 = unlimited until server stops giving)
MAX_CLAIMS = int(os.environ.get("MAX_CLAIMS", "30"))
# Cooldown between claims (seconds)
COOLDOWN = float(os.environ.get("COOLDOWN", "3"))
# Max consecutive failures before stopping
MAX_CONSECUTIVE_FAILS = int(os.environ.get("MAX_FAILS", "5"))
# Headless mode
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"
# Enable daily reward claim
CLAIM_DAILY = os.environ.get("CLAIM_DAILY", "true").lower() == "true"
# Log file
LOG_FILE = os.environ.get("LOG_FILE", "sam_reward_log.json")

# ============================================================
# Logging
# ============================================================
log_entries = []
balance_history = []

def log(msg, level="INFO"):
    """Print + save to log."""
    timestamp = datetime.now().isoformat()
    entry = {"time": timestamp, "level": level, "message": msg}
    log_entries.append(entry)
    print(f"[{timestamp[11:19]}] {msg}", flush=True)

def save_log():
    """Save log + balance history to JSON."""
    output = {
        "run_date": datetime.now().isoformat(),
        "config": {
            "max_claims": MAX_CLAIMS,
            "cooldown": COOLDOWN,
            "headless": HEADLESS,
            "claim_daily": CLAIM_DAILY,
        },
        "log": log_entries,
        "balance_history": balance_history,
        "summary": {
            "total_claims_attempted": len([e for e in log_entries if "Claim" in e["message"] and "✅" in e["message"]]),
            "total_reward": sum(b.get("reward", 0) for b in balance_history if b.get("reward")),
        },
    }
    with open(LOG_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    log(f"Log saved to {LOG_FILE}")


# ============================================================
# Bot functions
# ============================================================
def get_balance(game_frame):
    """Get current coin balance."""
    try:
        return game_frame.evaluate("() => document.querySelector('.chipBalance')?.textContent.trim() || 'unknown'")
    except:
        return "unknown"

def parse_balance(balance_str):
    """Parse balance string like '23.49k' to number."""
    if not balance_str or balance_str == 'unknown':
        return 0
    try:
        s = balance_str.lower().replace(',', '').strip()
        if 'k' in s:
            return int(float(s.replace('k', '')) * 1000)
        elif 'm' in s:
            return int(float(s.replace('m', '')) * 1000000)
        else:
            return int(float(s))
    except:
        return 0

def claim_video_reward(game_frame, page):
    """Send VIDEO_REWARD WS message. Returns {success, amount}.
    
    Includes WS health check + page reload if disconnected.
    """
    # Check WS connection health
    try:
        ws_ok = game_frame.evaluate("""
            () => {
                if (!window.connection || !connection.ws) return false;
                return connection.ws.readyState === 1;
            }
        """)
        if not ws_ok:
            log("  ⚠️ WS disconnected — reloading game...", "WARN")
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(15000)
            # Re-find game frame
            for f in page.frames:
                if "apps-" in f.url and "fbsbx.com" in f.url and "instant-bundle" in f.url:
                    game_frame = f
                    break
            if not game_frame:
                return {"success": False, "error": "game frame lost after reload"}
            page.wait_for_timeout(5000)
            log("  ✅ Game reloaded", "INFO")
    except Exception as e:
        log(f"  ⚠️ WS check error: {e}", "WARN")
    
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
                                    if (window.Ads.RewardedVideo.showUI) 
                                        window.Ads.RewardedVideo.showUI();
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
                        if (!resolved) {
                            resolved = true;
                            resolve({success: false, error: 'timeout'});
                        }
                    }, 8000);
                } catch(e) {
                    resolve({success: false, error: e.toString()});
                }
            });
        }
    """)
    return result, game_frame

def claim_daily_reward(game_frame):
    """Claim daily reward via dailyReward.show()."""
    try:
        result = game_frame.evaluate("""
            () => {
                return new Promise((resolve) => {
                    try {
                        // Check if dailyReward exists
                        if (typeof dailyReward === 'undefined' || !dailyReward) {
                            resolve({success: false, error: 'dailyReward not available'});
                            return;
                        }
                        
                        // Call show() to open daily reward dialog
                        dailyReward.show();
                        
                        // Wait a moment for dialog to appear
                        setTimeout(() => {
                            // Look for "claim" / "nhận" button in the dialog
                            const dialogs = document.querySelectorAll('[class*="msgBox"], [class*="dialog"]');
                            for (const d of dialogs) {
                                if (d.offsetParent !== null && d.textContent.trim()) {
                                    const buttons = d.querySelectorAll('button, input[type="button"], [onclick]');
                                    for (const b of buttons) {
                                        const txt = (b.textContent || b.value || '').toLowerCase();
                                        if (/claim|nhận|ok|ok|đồng ý|confirm|collect/i.test(txt)) {
                                            b.click();
                                            resolve({success: true, button: txt});
                                            return;
                                        }
                                    }
                                }
                            }
                            // Try calling dailyReward.claim() if exists
                            if (typeof dailyReward.claim === 'function') {
                                dailyReward.claim();
                                resolve({success: true, method: 'claim()'});
                                return;
                            }
                            resolve({success: false, error: 'no claim button found'});
                        }, 2000);
                    } catch(e) {
                        resolve({success: false, error: e.toString()});
                    }
                });
            }
        """)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("FB Sam Loc Reward Bot v2")
    print("=" * 60)
    print(f"Max claims:     {MAX_CLAIMS if MAX_CLAIMS > 0 else 'unlimited'}")
    print(f"Cooldown:       {COOLDOWN}s")
    print(f"Max consec fail:{MAX_CONSECUTIVE_FAILS}")
    print(f"Claim daily:    {CLAIM_DAILY}")
    print(f"Headless:       {HEADLESS}")
    print(f"Log file:       {LOG_FILE}")
    print()
    
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
        
        # Login FB
        log("[1] Login Facebook...")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
        email_input = page.locator('input[placeholder="Email or phone"]').count()
        if email_input > 0:
            log("  ❌ Not logged in. Check FB_COOKIES.", "ERROR")
            browser.close()
            save_log()
            return 1
        log("  ✅ Logged in")
        
        # Open game
        log("[2] Open Sam loc game...")
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(20000)
        
        game_frame = None
        for f in page.frames:
            if "apps-" in f.url and "fbsbx.com" in f.url and "instant-bundle" in f.url:
                game_frame = f
                break
        
        if not game_frame:
            log("  ❌ Game frame not found", "ERROR")
            browser.close()
            save_log()
            return 1
        
        log("  ✅ Game loaded")
        page.wait_for_timeout(5000)
        
        # Get initial balance
        balance_start = get_balance(game_frame)
        balance_start_num = parse_balance(balance_start)
        log(f"[3] Starting balance: {balance_start} ({balance_start_num:,})")
        balance_history.append({
            "time": datetime.now().isoformat(),
            "balance": balance_start,
            "balance_num": balance_start_num,
            "event": "start",
        })
        
        # Claim daily reward first (if enabled)
        if CLAIM_DAILY:
            log("[4] Claiming daily reward...")
            daily_result = claim_daily_reward(game_frame)
            log(f"  Daily reward: {daily_result}")
            if daily_result.get('success'):
                time.sleep(2)
                balance_after_daily = get_balance(game_frame)
                log(f"  Balance after daily: {balance_after_daily}")
                balance_history.append({
                    "time": datetime.now().isoformat(),
                    "balance": balance_after_daily,
                    "balance_num": parse_balance(balance_after_daily),
                    "event": "daily_reward",
                    "result": daily_result,
                })
        
        # Main reward loop
        log(f"\n[5] Starting reward loop (max {MAX_CLAIMS} claims, cooldown {COOLDOWN}s)...")
        total_reward = 0
        success_count = 0
        fail_count = 0
        consecutive_fails = 0
        reward_sequence = []
        
        max_iterations = MAX_CLAIMS if MAX_CLAIMS > 0 else 999
        i = 0
        
        while i < max_iterations:
            i += 1
            try:
                balance_before = get_balance(game_frame)
                balance_before_num = parse_balance(balance_before)
                
                log(f"Claim {i}: ")
                result, game_frame = claim_video_reward(game_frame, page)
                
                if result.get('success'):
                    amount = result.get('amount', 0)
                    if amount > 0:
                        success_count += 1
                        consecutive_fails = 0
                        total_reward += amount
                        reward_sequence.append(amount)
                        log(f"✅ +{amount} coin (total: {total_reward:,})")
                        
                        # Wait for balance to update
                        time.sleep(1)
                        balance_after = get_balance(game_frame)
                        balance_after_num = parse_balance(balance_after)
                        log(f" | Balance: {balance_before} → {balance_after}")
                        
                        balance_history.append({
                            "time": datetime.now().isoformat(),
                            "claim_num": i,
                            "balance_before": balance_before,
                            "balance_after": balance_after,
                            "balance_num_before": balance_before_num,
                            "balance_num_after": balance_after_num,
                            "reward": amount,
                            "event": "claim_success",
                        })
                    else:
                        fail_count += 1
                        consecutive_fails += 1
                        log(f"⚠️ Success but amount=0 ({result.get('error', '')})")
                else:
                    fail_count += 1
                    consecutive_fails += 1
                    log(f"❌ {result.get('error', 'failed')}")
                
                # Save log every 5 claims
                if i % 5 == 0:
                    save_log()
                
                # Check if too many consecutive fails
                if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                    log(f"\n⚠️ {MAX_CONSECUTIVE_FAILS} consecutive fails — stopping", "WARN")
                    break
                
                # Cooldown
                if i < max_iterations:
                    time.sleep(COOLDOWN)
            except Exception as e:
                log(f"❌ Exception in claim {i}: {e}", "ERROR")
                import traceback
                traceback.print_exc()
                consecutive_fails += 1
                if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                    log(f"Too many fails after exceptions — stopping", "WARN")
                    break
                # Try to recover by reloading
                try:
                    log("  Reloading game to recover...", "WARN")
                    page.reload(wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(15000)
                    for f in page.frames:
                        if "apps-" in f.url and "fbsbx.com" in f.url and "instant-bundle" in f.url:
                            game_frame = f
                            break
                    page.wait_for_timeout(5000)
                    log("  ✅ Recovered", "INFO")
                except Exception as e2:
                    log(f"  ❌ Recovery failed: {e2}", "ERROR")
                    break
        
        # Final summary
        balance_end = get_balance(game_frame)
        balance_end_num = parse_balance(balance_end)
        actual_gain = balance_end_num - balance_start_num
        
        log("")
        log("=" * 60)
        log("FINAL SUMMARY")
        log("=" * 60)
        log(f"  Claims attempted:  {i}")
        log(f"  Success:           {success_count}")
        log(f"  Failed:            {fail_count}")
        log(f"  Total reward:      {total_reward:,} coin")
        log(f"  Balance start:     {balance_start} ({balance_start_num:,})")
        log(f"  Balance end:       {balance_end} ({balance_end_num:,})")
        log(f"  Actual gain:       {actual_gain:,} coin")
        log(f"  Reward sequence:   {reward_sequence}")
        
        balance_history.append({
            "time": datetime.now().isoformat(),
            "balance": balance_end,
            "balance_num": balance_end_num,
            "event": "end",
            "total_reward": total_reward,
            "actual_gain": actual_gain,
        })
        
        save_log()
        browser.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
