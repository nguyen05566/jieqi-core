#!/usr/bin/env python3
"""FB Tien Len Mien Nam reward bot v9 — BATCH TRANSFER MODE
★ Claim 40 lần rồi transfer, lặp lại cho đến hết MAX_RUNTIME
Login FB và load game 1 LẦN duy nhất ở đầu session, sau đó:
  loop: claim 40 lần → transfer → claim 40 lần → transfer → ... cho tới hết MAX_RUNTIME"""

import os, sys, time, re, random

# Thử import module bổ trợ nếu có (không bắt buộc)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

GAME_URL = "https://www.facebook.com/gaming/play/tienlen_miennam"
CLAIM_BATCH = int(os.environ.get("CLAIM_BATCH", "40"))  # Số claim trước khi transfer
MAX_CYCLES = CLAIM_BATCH
DELAY = float(os.environ.get("COOLDOWN", "3"))
REST = int(os.environ.get("REST_BETWEEN_RUNS", "3"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

# ============ TRANSFER LOGIC ============
# Transfer xu về hub account sau mỗi CLAIM_BATCH lần claim
TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "51977054"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"

# ============ SINGLE COOKIE MODE ============
SINGLE_COOKIE_FILE = os.environ.get("SINGLE_COOKIE_FILE", "ck1.txt").strip()

# ============ Pre-claim transfer threshold ============
# Nếu balance > ngưỡng này (xu), transfer trước khi claim tiếp
PRE_CLAIM_TRANSFER_THRESHOLD = int(os.environ.get("PRE_CLAIM_TRANSFER_THRESHOLD", "10000"))


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


# ============================================================
# ĐỌC COOKIE TỪ FILE DUY NHẤT
# ============================================================
def load_single_cookie_set(path):
    """Đọc đúng 1 file cookie. Trả về [{"file": "...", "raw": "..."}] hoặc []."""
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

    # Chuẩn hoá: bỏ nháy, gộp xuống dòng/tab, chuẩn hoá dấu ;
    content = content.strip('"').strip("'")
    content = " ".join(content.split())
    content = content.replace(";  ", "; ").replace(" ;", ";")

    print(f"[COOKIE] ✅ Nạp {os.path.basename(path)} ({len(content)} ký tự)", flush=True)
    return [{"file": os.path.basename(path), "raw": content}]


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


def simulate_human(gf, page):
    """Mô phỏng hành vi người (di chuyển chuột, cuộn trang)"""
    try:
        page.mouse.move(
            random.randint(100, 800),
            random.randint(100, 600)
        )
        scroll_amount = random.randint(-50, 50)
        gf.evaluate(f"window.scrollBy(0, {scroll_amount})")
        time.sleep(random.uniform(0.5, 1.5))
    except:
        pass


def transfer_all_xu(gf, page, dest_id=TRANSFER_DEST_ID):
    """Transfer ALL current xu về dest_id via game's connection.send.

    If WS not connected, reload page (via ensure_ws_connected) and retry.
    Returns dict {success, amount, status, message}.
    """
    # Ensure WS is connected (reload page if needed)
    if not ensure_ws_connected(gf, page):
        return {"success": False, "error": "ws reconnect failed after reloads"}

    # After reload, re-find game frame (gf may have changed)
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


def find_gf(page, max_wait=120):
    """Find game frame. Default 120s (game takes 30-60s to load)."""
    for _ in range(max_wait // 5):
        for f in page.frames:
            if "instant-bundle" in f.url and "fbsbx.com" in f.url:
                return f
        time.sleep(5)
    return None


def is_account_blocked(gf):
    """Check if any visible alert dialog says account is blocked.

    Returns True if account is blocked (skip this cookie entirely).
    """
    try:
        blocked = gf.evaluate("""() => {
            const dialogs = document.querySelectorAll('[class*="msgBox"], [class*="dialog"], [class*="Dialog"], [class*="alert"]');
            for (const d of dialogs) {
                if (d.offsetParent === null) continue;
                const txt = (d.textContent || '').toLowerCase();
                if (txt.includes('blocked') || txt.includes('khóa') || txt.includes('cấm') || txt.includes('tạm khóa')) {
                    return true;
                }
            }
            return false;
        }""")
        return bool(blocked)
    except Exception:
        return False


def ensure_ws_connected(gf, page, max_retries=2):
    """Check WS state, reload page if disconnected.
    Returns True if WS is now connected (after possible reload).
    """
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
                    print("[WS] ✅ Reconnected", flush=True)
                    return True
        except Exception as e:
            print(f"[WS] ⚠️ Reload error: {e}", flush=True)
            time.sleep(5)
    print("[WS] ❌ Reconnect failed after retries", flush=True)
    return False


def click_claim_button(gf):
    """Click the claim button in the game."""
    try:
        gf.evaluate("""() => {
            const btn = document.querySelector('[class*="claim"], [class*="Claim"], [class*="nhận"], [class*="Nhận"]');
            if (btn && btn.offsetParent !== null) {
                btn.click();
                return true;
            }
            return false;
        }""")
        return True
    except Exception as e:
        print(f"[CLAIM] ❌ Error: {e}", flush=True)
        return False


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
        
        # Find game frame
        gf = find_gf(page, max_wait=120)
        if not gf:
            print("[MAIN] ❌ Game frame not found", flush=True)
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
                # STEP 1: Simulate human behavior
                simulate_human(gf, page)
                
                # STEP 2: Click claim button
                if not click_claim_button(gf):
                    print(f"[CLAIM] ⚠️ Claim button not found (attempt {i+1})", flush=True)
                    time.sleep(2)
                    continue
                
                # STEP 3: Wait for delay
                time.sleep(DELAY)
                
                total_claims += 1
                bal = get_bal(gf)
                print(f"[CLAIM] ✅ #{total_claims} | Balance: {bal}", flush=True)
                
                # Check balance threshold for pre-claim transfer
                bal_num = parse_balance_num(bal)
                if bal_num > PRE_CLAIM_TRANSFER_THRESHOLD and TRANSFER_ENABLED:
                    print(f"[TRANSFER] Balance > threshold ({PRE_CLAIM_TRANSFER_THRESHOLD}), transferring...", flush=True)
                    transfer_result = transfer_all_xu(gf, page)
                    print(f"[TRANSFER] Result: {transfer_result}", flush=True)
            
            # Transfer after batch
            if TRANSFER_ENABLED:
                print(f"[TRANSFER] Transferring after {CLAIM_BATCH} claims...", flush=True)
                transfer_result = transfer_all_xu(gf, page)
                print(f"[TRANSFER] Result: {transfer_result}", flush=True)
            
            # Rest between runs
            if time.time() - start_time < MAX_RUNTIME:
                print(f"[MAIN] Resting for {REST}s...", flush=True)
                time.sleep(REST)
        
        print(f"[MAIN] ✅ Completed {total_claims} claims in {(time.time()-start_time)/60:.1f} minutes", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
