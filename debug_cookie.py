#!/usr/bin/env python3
"""debug_cookie.py — Diagnose why a cookie fails all claims.

Walks through each step of trigger_and_claim and dumps state at each point:
1. Login FB + open game + wait WS
2. Check .chipBalance existence (why balance = ?)
3. Check createTable function exists
4. Try createTable() — see what dialog appears
5. Check radio_11 element
6. Check CREATE button
7. Check "enough coin" dialog after CREATE click
8. Check "watch" button click
9. Check OutboundMessage + connection.send exists
10. Try VIDEO_REWARD cmd — log server response

Usage: python3 debug_cookie.py <ckN.txt>
"""
import sys, os, time, re
sys.path.insert(0, "/home/z/my-project/scripts/sam_bot")
from sam_reward_bot_v3_transfer import parse_cookie, find_gf, get_bal, GAME_URL
from playwright.sync_api import sync_playwright

def main():
    ck_file = sys.argv[1] if len(sys.argv) > 1 else "ck2.txt"
    ck_path = os.path.join("/home/z/my-project/scripts/sam_bot", ck_file)
    if not os.path.exists(ck_path):
        print(f"❌ {ck_path} not found")
        return 1
    
    with open(ck_path) as f:
        cookies_str = f.read().strip()
    fb_cookies = parse_cookie(cookies_str)
    cuser = re.search(r'c_user=(\d+)', cookies_str)
    print(f"=== Debug cookie: {ck_file} (c_user={cuser.group(1) if cuser else '?'}) ===")
    print(f"  Loaded {len(fb_cookies)} cookies")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")
        for c in fb_cookies: c['domain'] = '.facebook.com'
        ctx.add_cookies(fb_cookies)
        page = ctx.new_page()
        
        # Step 1: Login FB
        print("\n[Step 1] Login FB...")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        sel = 'input[placeholder="Email or phone"]'
        login_inputs = page.locator(sel).count()
        if login_inputs > 0:
            print(f"  ❌ Not logged in — cookie expired")
            browser.close()
            return 1
        print(f"  ✓ Logged in")
        
        # Step 2: Open game
        print(f"\n[Step 2] Open game: {GAME_URL}")
        page.goto(GAME_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(20000)  # 20s for game to start loading
        
        # Find game frame
        gf = find_gf(page, max_wait=120)
        if not gf:
            print(f"  ❌ Game frame not found after 120s")
            # Print all frames
            print(f"  All frames:")
            for f in page.frames:
                print(f"    {f.url[:100]}")
            browser.close()
            return 1
        print(f"  ✓ Game frame: {gf.url[:80]}")
        
        # Wait extra for game to fully init
        page.wait_for_timeout(15000)
        
        # Step 3: Check WS state
        print(f"\n[Step 3] Check WS state...")
        try:
            ws_state = gf.evaluate("""() => ({
                hasConnection: typeof window.connection,
                hasWs: window.connection ? typeof window.connection.ws : 'no',
                wsReadyState: window.connection && connection.ws ? connection.ws.readyState : null,
                wsUrl: window.connection && connection.ws ? connection.ws.url : null,
            })""")
            print(f"  connection: {ws_state.get('hasConnection')}")
            print(f"  ws: {ws_state.get('hasWs')}")
            ready = ws_state.get('wsReadyState')
            print(f"  wsReadyState: {ready} ({'CONNECTING' if ready==0 else 'OPEN' if ready==1 else 'CLOSING' if ready==2 else 'CLOSED' if ready==3 else 'null'})")
            print(f"  wsUrl: {ws_state.get('wsUrl')}")
        except Exception as e:
            print(f"  ❌ evaluate error: {e}")
        
        # Step 4: Check chipBalance DOM
        print(f"\n[Step 4] Check chipBalance DOM...")
        try:
            dom_state = gf.evaluate("""() => {
                const out = {};
                // Check chipBalance element
                const bal = document.querySelector('.chipBalance');
                out.chipBalance_exists = !!bal;
                out.chipBalance_text = bal ? bal.textContent.trim() : null;
                // Check other chip-related elements
                const chipEls = document.querySelectorAll('[class*="chip"], [class*="Chip"], [class*="balance"], [class*="Balance"]');
                out.chip_elements_count = chipEls.length;
                out.chip_elements_sample = Array.from(chipEls).slice(0, 5).map(e => ({
                    class: e.className.substring(0, 60),
                    text: (e.textContent || '').trim().substring(0, 40)
                }));
                // Check body HTML length (game loaded?)
                out.body_HTML_length = document.body ? document.body.innerHTML.length : 0;
                // Check window globals
                out.has_createTable = typeof window.createTable;
                out.has_OutboundMessage = typeof window.OutboundMessage;
                out.has_Ads = typeof window.Ads;
                out.Ads_RewardedVideo = window.Ads && window.Ads.RewardedVideo ? Object.keys(window.Ads.RewardedVideo).slice(0, 10) : null;
                return out;
            }""")
            print(f"  chipBalance exists: {dom_state.get('chipBalance_exists')}")
            print(f"  chipBalance text: {dom_state.get('chipBalance_text')!r}")
            print(f"  chip elements count: {dom_state.get('chip_elements_count')}")
            print(f"  chip elements sample:")
            for s in dom_state.get('chip_elements_sample', []):
                print(f"    class={s['class']!r} text={s['text']!r}")
            print(f"  body HTML length: {dom_state.get('body_HTML_length')}")
            print(f"  window.createTable: {dom_state.get('has_createTable')}")
            print(f"  window.OutboundMessage: {dom_state.get('has_OutboundMessage')}")
            print(f"  window.Ads: {dom_state.get('has_Ads')}")
            print(f"  Ads.RewardedVideo keys: {dom_state.get('Ads_RewardedVideo')}")
        except Exception as e:
            print(f"  ❌ evaluate error: {e}")
        
        # Step 5: Try createTable() and see what dialog appears
        print(f"\n[Step 5] Try createTable()...")
        try:
            create_result = gf.evaluate("""() => {
                try {
                    if (typeof createTable !== 'function') {
                        return {error: 'createTable is not a function', type: typeof createTable};
                    }
                    createTable();
                    return {success: true};
                } catch(e) {
                    return {error: e.toString()};
                }
            }""")
            print(f"  Result: {create_result}")
        except Exception as e:
            print(f"  ❌ evaluate error: {e}")
        time.sleep(3)
        
        # Step 6: Check radio_11 (bet selection)
        print(f"\n[Step 6] Check radio_11 + bet selection...")
        try:
            radio_state = gf.evaluate("""() => {
                const r = document.getElementById('radio_11');
                const allRadios = document.querySelectorAll('input[type="radio"][name="betAmt"]');
                const createBtn = document.querySelector('input[name="CREATE"]');
                return {
                    radio_11_exists: !!r,
                    all_radios_count: allRadios.length,
                    all_radios_ids: Array.from(allRadios).map(r => r.id).slice(0, 10),
                    create_btn_exists: !!createBtn,
                };
            }""")
            print(f"  radio_11 exists: {radio_state.get('radio_11_exists')}")
            print(f"  all radios count: {radio_state.get('all_radios_count')}")
            print(f"  radio ids: {radio_state.get('all_radios_ids')}")
            print(f"  CREATE button exists: {radio_state.get('create_btn_exists')}")
        except Exception as e:
            print(f"  ❌ evaluate error: {e}")
        
        # Step 7: Click CREATE button and check dialog
        print(f"\n[Step 7] Click CREATE button → check 'enough coin' dialog...")
        try:
            gf.evaluate("""() => {
                const r = document.getElementById('radio_11');
                if (r) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }
                const b = document.querySelector('input[name="CREATE"]');
                if (b) b.click();
            }""")
            time.sleep(3)
            dialog_state = gf.evaluate("""() => {
                const dialogs = document.querySelectorAll('[class*="msgBox"]');
                const result = [];
                for (const d of dialogs) {
                    if (d.offsetParent === null) continue;
                    const text = (d.textContent || '').trim().substring(0, 200);
                    const buttons = d.querySelectorAll('input[type="button"], button');
                    const btn_texts = Array.from(buttons).map(b => (b.value || b.textContent || '').trim().substring(0, 30));
                    result.push({text: text, buttons: btn_texts});
                }
                return {dialog_count: dialogs.length, dialogs: result};
            }""")
            print(f"  Dialog count: {dialog_state.get('dialog_count')}")
            for i, d in enumerate(dialog_state.get('dialogs', [])):
                print(f"  Dialog {i}: text={d['text']!r}")
                print(f"             buttons={d['buttons']}")
        except Exception as e:
            print(f"  ❌ evaluate error: {e}")
        
        # Step 8: Send VIDEO_REWARD cmd directly + log response
        print(f"\n[Step 8] Send VIDEO_REWARD cmd + log full response...")
        try:
            vr_result = gf.evaluate("""() => {
                return new Promise((resolve) => {
                    try {
                        if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                            resolve({error: 'ws not connected', readyState: window.connection?.ws?.readyState});
                            return;
                        }
                        if (typeof OutboundMessage !== 'function') {
                            resolve({error: 'OutboundMessage not defined'});
                            return;
                        }
                        const msg = new OutboundMessage("VIDEO_REWARD");
                        msg.writeByte(1);
                        let resolved = false;
                        connection.send(msg, function(resp, success) {
                            if (resolved) return;
                            resolved = true;
                            try {
                                const allKeys = Object.keys(resp || {});
                                let amount = null;
                                try { amount = resp.readLong(); } catch(e) {}
                                let status = null;
                                try { status = resp.readSignedByte(); } catch(e) {}
                                resolve({success: success, amount: amount, status: status, resp_keys: allKeys});
                            } catch(e) {
                                resolve({success: success, error: e.toString()});
                            }
                        });
                        setTimeout(() => {
                            if (!resolved) { resolved = true; resolve({error: 'timeout after 20s'}); }
                        }, 20000);
                    } catch(e) {
                        resolve({error: e.toString()});
                    }
                });
            }""")
            print(f"  VIDEO_REWARD result: {vr_result}")
        except Exception as e:
            print(f"  ❌ evaluate error: {e}")
        
        # Done
        print(f"\n[Done] Diagnosis complete. Check the output above to identify issue.")
        try:
            page.screenshot(path=f"/tmp/debug_{ck_file.replace('.txt', '')}.png", full_page=True)
            print(f"  Screenshot saved: /tmp/debug_{ck_file.replace('.txt', '')}.png")
        except:
            pass
        browser.close()

if __name__ == "__main__":
    sys.exit(main())
