#!/usr/bin/env python3
"""FB Phom Tala reward bot v11 — FIXED: Claim Button Not Found
★ Fix: Chờ game load xong + Sửa selector button + Debug
"""

import os, sys, time, re, random

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

GAME_URL = "https://www.facebook.com/gaming/play/phom_tala"
CLAIM_BATCH = int(os.environ.get("CLAIM_BATCH", "40"))
MAX_CYCLES = CLAIM_BATCH
DELAY = float(os.environ.get("COOLDOWN", "3"))
REST = int(os.environ.get("REST_BETWEEN_RUNS", "5"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "71391352"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"
SINGLE_COOKIE_FILE = os.environ.get("SINGLE_COOKIE_FILE", "ck2.txt").strip()
PRE_CLAIM_TRANSFER_THRESHOLD = int(os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000"))

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

def load_single_cookie_set(path):
    if not os.path.exists(path):
        print(f"[COOKIE] ❌ Không tìm thấy file: {path}", flush=True)
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
    except Exception as e:
        print(f"[COOKIE] ❌ Lỗi đọc {path}: {e}", flush=True)
        return []
    if not content:
        print(f"[COOKIE] ❌ {path} rỗng", flush=True)
        return []
    content = content.strip('"').strip("'")
    content = " ".join(content.split())
    content = content.replace(";  ", "; ").replace(" ;", ";")
    print(f"[COOKIE] ✅ Nạp {os.path.basename(path)} ({len(content)} ký tự)", flush=True)
    return [{"file": os.path.basename(path), "raw": content}]

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

def get_bal(gf):
    try:
        selectors = [
            '.chipBalance', '.coinBalance', '.goldBalance',
            '.balanceText', '.currencyAmount', '[class*="balance"]',
            '[class*="Balance"]', '[class*="xu"]', '[class*="Xu"]'
        ]
        for selector in selectors:
            bal = gf.evaluate(f"""() => {{
                const el = document.querySelector('{selector}');
                return el ? el.textContent.trim() : null;
            }}""")
            if bal and bal != '?' and bal != '0':
                return bal
        return "?"
    except Exception:
        return "?"

def find_gf(page, max_wait=120):
    """Find game frame"""
    for _ in range(max_wait // 5):
        for f in page.frames:
            if "instant-bundle" in f.url and "fbsbx.com" in f.url:
                return f
        time.sleep(5)
    return None

def is_game_frame_ready(gf):
    """Kiểm tra game frame đã sẵn sàng chưa"""
    try:
        ready = gf.evaluate("""() => {
            if (!window.connection || !connection.ws || connection.ws.readyState !== 1) {
                return false;
            }
            const gameLoaded = document.querySelector('.game-loaded, .game-ready, [class*="loaded"], [class*="ready"]');
            return !!gameLoaded;
        }""")
        return bool(ready)
    except:
        return False

def wait_for_game_ready(gf, timeout=120):
    """Chờ game tải xong và button claim xuất hiện"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            selectors = [
                '[class*="claim"]', '[class*="Claim"]',
                '[class*="nhận"]', '[class*="Nhận"]',
                '[class*="reward"]', '[class*="Reward"]',
                '[class*="collect"]', '[class*="Collect"]',
                '[class*="phom"]', '[class*="Phom"]',
                '[class*="tala"]', '[class*="Tala"]'
            ]

            for selector in selectors:
                button_exists = gf.evaluate(f"""() => {{
                    const btn = document.querySelector('{selector}');
                    return btn && btn.offsetParent !== null;
                }}""")
                if button_exists:
                    print(f"[GAME] ✅ Found claim button: {selector}", flush=True)
                    return True

            print("[GAME] ⏳ Waiting for claim button...", flush=True)
            time.sleep(5)

        except Exception as e:
            print(f"[GAME] ⚠️ Error: {e}", flush=True)
            time.sleep(5)

    print("[GAME] ❌ Claim button not found after timeout", flush=True)
    return False

def debug_game_state(gf):
    """In ra trạng thái game để debug"""
    try:
        state = gf.evaluate("""() => {
            return {
                hasConnection: !!(window.connection && connection.ws),
                wsReady: window.connection?.ws?.readyState === 1,
                hasBalance: !!document.querySelector('.chipBalance, .coinBalance, [class*="balance"]'),
                hasClaimBtn: !!document.querySelector('[class*="claim"], [class*="Claim"], [class*="nhận"]'),
                visibleButtons: Array.from(document.querySelectorAll('button')).slice(0, 5).map(b => b.textContent?.trim() || '')
            };
        }""")
        print(f"[DEBUG] Connection: {state.get('hasConnection')}, WS Ready: {state.get('wsReady')}", flush=True)
        print(f"[DEBUG] Has Balance: {state.get('hasBalance')}, Has Claim Btn: {state.get('hasClaimBtn')}", flush=True)
        print(f"[DEBUG] Visible Buttons: {state.get('visibleButtons')}", flush=True)
        return state
    except Exception as e:
        print(f"[DEBUG] Error: {e}", flush=True)
        return {}

def click_claim_button(gf):
    """Click claim button với NHIỀU SELECTOR"""
    try:
        selectors = [
            '[class*="claim"]', '[class*="Claim"]',
            '[class*="nhận"]', '[class*="Nhận"]',
            '[class*="reward"]', '[class*="Reward"]',
            '[class*="collect"]', '[class*="Collect"]',
            '[class*="phom"]', '[class*="Phom"]',
            '[class*="tala"]', '[class*="Tala"]',
            'button.claim-button', 'button.reward-button',
            '.claim-reward-btn', '.collect-btn',
            '[data-testid="claim-button"]', '[data-testid="reward-button"]'
        ]

        for selector in selectors:
            try:
                clicked = gf.evaluate(f"""() => {{
                    const btn = document.querySelector('{selector}');
                    if (btn && btn.offsetParent !== null && !btn.disabled) {{
                        btn.click();
                        return true;
                    }}
                    return false;
                }}""")
                if clicked:
                    print(f"[CLAIM] ✅ Clicked with selector: {selector}", flush=True)
                    return True
            except:
                continue

        # Thử click bằng text content
        print("[CLAIM] ⚠️ Trying text-based selectors...", flush=True)
        clicked = gf.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.offsetParent === null || btn.disabled) continue;
                const text = (btn.textContent || '').toLowerCase();
                if (text.includes('claim') || text.includes('nhận') || text.includes('thu') || text.includes('collect')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        return clicked

    except Exception as e:
        print(f"[CLAIM] ❌ Error: {e}", flush=True)
        return False

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

def ensure_ws_connected(gf, page, max_retries=2):
    try:
        ws_ok = gf.evaluate("() => !!(window.connection && connection.ws && connection.ws.readyState === 1)")
        if ws_ok:
            return True
    except Exception:
        pass
    for retry in range(max_retries):
        try:
            print(f"[WS] Reloading page (attempt {retry + 1}/{max_retries})...", flush=True)
            page.reload()
            time.sleep(15)
            gf_new = find_gf(page, max_wait=60)
            if gf_new:
                gf = gf_new
                ws_ok = gf.evaluate("() => !!(window.connection && connection.ws && connection.ws.readyState === 1)")
                if ws_ok:
                    return True
        except Exception as e:
            print(f"[WS] ⚠️ Error: {e}", flush=True)
            time.sleep(5)
    return False

def transfer_all_xu(gf, page, dest_id=TRANSFER_DEST_ID):
    if not ensure_ws_connected(gf, page):
        return {"success": False, "error": "ws reconnect failed after reloads"}
    gf_new = find_gf(page, max_wait=30)
    if gf_new:
        gf = gf_new
    try:
        result = gf.evaluate("""(destId) => {
            return new Promise((resolve) => {
                try {
                    const balEl = document.querySelector('.chipBalance, .coinBalance, [class*="balance"]');
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

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        # Load cookie
        cookie_set = load_single_cookie_set(SINGLE_COOKIE_FILE)
        if not cookie_set:
            print("[MAIN] ❌ No valid cookie file", flush=True)
            browser.close()
            return

        # Add cookie to browser
        parsed_cookies = parse_cookie(cookie_set[0]['raw'])
        context.add_cookies(parsed_cookies)

        # Navigate to game
        print(f"[MAIN] 🎮 Navigating to {GAME_URL}...", flush=True)
        page.goto(GAME_URL, timeout=120000)

        # 👇 CHỜ 30S SAU KHI LOAD GAME
        print("[MAIN] ⏳ Waiting for game to initialize...", flush=True)
        time.sleep(30)

        # Find game frame
        gf = find_gf(page, max_wait=120)
        if not gf:
            print("[MAIN] ❌ Game frame not found", flush=True)
            browser.close()
            return

        # 👇 CHỜ GAME FRAME SẴN SÀNG
        if not wait_for_game_ready(gf, timeout=120):
            print("[MAIN] ❌ Game not ready", flush=True)
            browser.close()
            return

        # Check if account is blocked
        if is_account_blocked(gf):
            print("[MAIN] ❌ Account is blocked", flush=True)
            browser.close()
            return

        print("[MAIN] ✅ Ready to claim", flush=True)
        start_time = time.time()
        total_claims = 0

        while time.time() - start_time < MAX_RUNTIME:
            for i in range(CLAIM_BATCH):
                if not click_claim_button(gf):
                    print(f"[CLAIM] ⚠️ Claim button not found (attempt {i+1})", flush=True)
                    debug_game_state(gf)  # 👈 DEBUG KHI KHÔNG TÌM THẤY
                    time.sleep(5)
                    continue

                time.sleep(DELAY)

                total_claims += 1
                bal = get_bal(gf)
                print(f"[CLAIM] ✅ #{total_claims} | Balance: {bal}", flush=True)

            if TRANSFER_ENABLED:
                print(f"[TRANSFER] Transferring after {CLAIM_BATCH} claims...", flush=True)
                transfer_result = transfer_all_xu(gf, page)
                print(f"[TRANSFER] Result: {transfer_result}", flush=True)

            if time.time() - start_time < MAX_RUNTIME:
                print(f"[MAIN] Resting for {REST}s...", flush=True)
                time.sleep(REST)

        print(f"[MAIN] ✅ Completed {total_claims} claims", flush=True)
        browser.close()

if __name__ == "__main__":
    main()
