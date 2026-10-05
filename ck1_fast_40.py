#!/usr/bin/env python3
"""FB Sam loc reward bot v9 — FAST MODE
★ Chạy 40 claims liên tục rồi transfer 1 lần
Sửa từ ck1.py: tăng tốc claim, giảm delay giữa các claim
"""
import os, sys, time, re

# Thử import module bổ trợ nếu có (không bắt buộc)
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

GAME_URL = "https://www.facebook.com/gaming/play/tienlen_miennam"
MAX_CYCLES = int(os.environ.get("MAX_CLAIMS", "40"))  # 40 claims rồi transfer
DELAY = float(os.environ.get("COOLDOWN", "0.5"))  # Giảm delay xuống 0.5s
REST = int(os.environ.get("REST_BETWEEN_RUNS", "5"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

# ============ TRANSFER LOGIC ============
# Transfer xu về hub account 68307415 sau mỗi session (40 claims)
TRANSFER_DEST_ID = int(os.environ.get("TRANSFER_DEST_ID", "68307415"))
TRANSFER_ENABLED = os.environ.get("TRANSFER_ENABLED", "true").lower() == "true"

# ============ SINGLE COOKIE MODE ============
SINGLE_COOKIE_FILE = os.environ.get("SINGLE_COOKIE_FILE", "ck1.txt").strip()

# ============ Pre-claim transfer threshold ============
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
    """
    Đọc đúng 1 file cookie. Trả về [{"file": "...", "raw": "..."}] hoặc [].
    """
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
def get_bal(gf):
    try:
        return gf.evaluate(
            "() => document.querySelector('.chipBalance')?.textContent.trim() || '?'"
        )
    except Exception:
        return "?"


def transfer_all_xu(gf, page, dest_id=TRANSFER_DEST_ID):
    """Transfer ALL current xu về dest_id via game's connection.send.

    If WS not connected, reload page (via ensure_ws_connected) and retry.
    Returns dict {success, amount, status, message}.
    """
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


def find_gf(page, max_wait=120):
    """Find game frame. Default 120s (game takes 30-60s to load)."""
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
    """Check WS state, reload page if disconnected."""
    try:
        ws_ok = gf.evaluate("() => !!(window.connection && connection.ws && connection.ws.readyState === 1)")
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

            for ws_check in range(15):
                try:
                    ws_ok = new_gf.evaluate("() => !!(window.connection && connection.ws && connection.ws.readyState === 1)")
                    if ws_ok:
                        print(f"  ✓ WS reconnected after reload #{retry+1}", flush=True)
                        return True
                except:
                    pass
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  ⚠ Reload #{retry+1} error: {e}", flush=True)
    return False


def trigger_and_claim(gf, page):
    """v3 logic + retry + WS reconnect before each claim.

    Now requires `page` to call ensure_ws_connected() if WS dies.
    """
    if not ensure_ws_connected(gf, page, max_retries=1):
        return {"success": False, "error": "ws reconnect failed"}
    gf_new = find_gf(page, max_wait=30)
    if gf_new:
        gf = gf_new

    try:
        gf.evaluate("createTable()")
    except Exception:
        pass
    time.sleep(1)  # Giảm từ 2s xuống 1s

    try:
        gf.evaluate("""() => {
            const btn = document.querySelector('button[class*="reward"][class*="claim"], button[class*="Claim"]');
            if (btn && btn.offsetParent !== null) {
                btn.click();
                return true;
            }
            return false;
        }""")
    except Exception:
        pass

    time.sleep(0.5)  # Giảm từ 2s xuống 0.5s

    try:
        clicked = gf.evaluate("""() => {
            const btn = document.querySelector('button[class*="reward"][class*="claim"], button[class*="Claim"]');
            if (btn && btn.offsetParent !== null && !btn.disabled) {
                btn.click();
                return true;
            }
            const btns = Array.from(document.querySelectorAll('button'));
            for (const b of btns) {
                if (b.offsetParent !== null && !b.disabled) {
                    const txt = (b.textContent || '').toLowerCase();
                    if (txt.includes('claim') || txt.includes('nhận') || txt.includes('reward')) {
                        b.click();
                        return true;
                    }
                }
            }
            return false;
        }""")
        if not clicked:
            return {"success": False, "error": "claim button not found"}
    except Exception as e:
        return {"success": False, "error": f"click error: {e}"}

    time.sleep(0.5)  # Giảm từ 3s xuống 0.5s

    # Wait for claim to complete
    for _ in range(10):  # 5s total wait
        try:
            status = gf.evaluate("""() => {
                const dialog = document.querySelector('[class*="msgBox"][class*="dialog"]');
                if (dialog && dialog.offsetParent !== null) {
                    const txt = (dialog.textContent || '').toLowerCase();
                    if (txt.includes('success') || txt.includes('thành công') || txt.includes('nhận')) {
                        return 'ok';
                    }
                    if (txt.includes('error') || txt.includes('lỗi') || txt.includes('fail')) {
                        return 'fail';
                    }
                }
                return 'waiting';
            }""")
            if status == 'ok':
                time.sleep(0.3)  # Giảm từ 1s xuống 0.3s
                return {"success": True}
            if status == 'fail':
                return {"success": False, "error": "claim failed"}
        except Exception:
            pass
        time.sleep(0.5)

    return {"success": False, "error": "claim timeout"}


def run_one_session(p, fb_cookies, session_id, started_at):
    """Mở browser → login → MAX_CYCLES (40) → transfer → close.
    Trả về (total, ok, fail, cookies_ok).
    """
    cookies_ok = 0
    total = 0
    ok = 0
    fail = 0
    grand_total_xu = 0

    with p.chromium.launch_persistent_context(
        user_data_dir=f"/tmp/pw_{session_id}",
        headless=HEADLESS,
        viewport={"width": 1280, "height": 720},
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--single-process",
        ],
    ) as context:
        page = context.new_page()
        page.set_default_timeout(60000)

        try:
            # ------- LOGIN -------
            print(f"[{session_id}] Login...", flush=True)
            page.goto(GAME_URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(15000)

            gf = find_gf(page, max_wait=120)
            if not gf:
                print(f"[{session_id}] ❌ Game frame not found", flush=True)
                return total, ok, fail, cookies_ok

            # Inject cookies
            cookie_list = parse_cookie(fb_cookies[0]["raw"])
            context.add_cookies(cookie_list)
            page.goto(GAME_URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(15000)
            gf = find_gf(page, max_wait=120)

            # Check blocked
            if is_account_blocked(gf):
                print(f"[{session_id}] ❌ Account blocked", flush=True)
                return total, ok, fail, cookies_ok

            # Reload until game loaded
            for _ in range(3):
                try:
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(20000)
                    gf = find_gf(page, max_wait=60)
                    if gf:
                        break
                except Exception:
                    pass
            if not gf:
                print(f"[{session_id}] ❌ Game frame not found after reloads", flush=True)
                return total, ok, fail, cookies_ok

            # Ensure WS connected
            if not ensure_ws_connected(gf, page, max_retries=2):
                print(f"[{session_id}] ❌ WS connection failed", flush=True)
                return total, ok, fail, cookies_ok

            bal_start = get_bal(gf)
            bal_start_num = parse_balance_num(bal_start)
            print(f"[{session_id}] Balance: {bal_start}", flush=True)

            # ===== Pre-claim transfer — if balance > threshold, transfer first =====
            if TRANSFER_ENABLED and bal_start_num > PRE_CLAIM_TRANSFER_THRESHOLD:
                print(f"\n[Pre-claim] Balance {bal_start_num:,} > {PRE_CLAIM_TRANSFER_THRESHOLD:,}, "
                      f"transferring first...", flush=True)
                try:
                    res = transfer_all_xu(gf, page)
                    if res.get("success"):
                        amt = res.get("balance", 0)
                        print(f"  ✅ Pre-claim transfer: {amt:,} xu → {TRANSFER_DEST_ID}", flush=True)
                    else:
                        err = res.get("error", "unknown")
                        print(f"  ❌ Pre-claim transfer fail: {err}", flush=True)
                except Exception as e:
                    print(f"  ❌ Pre-claim transfer exception: {e}", flush=True)
            else:
                print(f"  (Balance {bal_start_num:,} ≤ {PRE_CLAIM_TRANSFER_THRESHOLD:,}, "
                      f"skip pre-claim transfer)", flush=True)

            # ===== REWARD LOOP =====
            print(f"\n[4] Reward loop ({MAX_CYCLES} cycles, delay={DELAY}s)...", flush=True)

            for i in range(MAX_CYCLES):
                total += 1
                bal = get_bal(gf)
                bal_num = parse_balance_num(bal)
                print(f"  [{i+1}/{MAX_CYCLES}] Balance: {bal} → Claiming...", flush=True)

                result = trigger_and_claim(gf, page)

                if result.get("success"):
                    ok += 1
                    new_bal = get_bal(gf)
                    new_bal_num = parse_balance_num(new_bal)
                    diff = new_bal_num - bal_num
                    print(f"    ✅ Claim OK! +{diff:,}", flush=True)
                    grand_total_xu += diff
                else:
                    fail += 1
                    err = result.get("error", "unknown")
                    print(f"    ❌ Claim FAIL: {err}", flush=True)

                # Wait before next claim
                if i < MAX_CYCLES - 1:
                    time.sleep(DELAY)  # Sử dụng DELAY (mặc định 0.5s)

                # Check WS and reconnect if needed
                try:
                    ws_ok = gf.evaluate("() => !!(window.connection && connection.ws && connection.ws.readyState === 1)")
                    if not ws_ok:
                        print(f"  ⚠ WS disconnected during loop, reconnecting...", flush=True)
                        if not ensure_ws_connected(gf, page, max_retries=1):
                            print(f"  ❌ WS reconnect failed, breaking loop", flush=True)
                            break
                except Exception:
                    pass

            # ===== FINAL TRANSFER =====
            print(f"\n[5] Final transfer...", flush=True)
            final_bal = get_bal(gf)
            final_bal_num = parse_balance_num(final_bal)
            print(f"  Final balance: {final_bal_num:,}", flush=True)

            if TRANSFER_ENABLED and final_bal_num > 200:
                try:
                    res = transfer_all_xu(gf, page)
                    if res.get("success"):
                        amt = res.get("balance", 0)
                        print(f"  ✅ Transfer: {amt:,} xu → {TRANSFER_DEST_ID}", flush=True)
                        grand_total_xu += amt
                    else:
                        err = res.get("error", "unknown")
                        print(f"  ❌ Transfer FAIL: {err}", flush=True)
                except Exception as e:
                    print(f"  ❌ Transfer exception: {e}", flush=True)
            else:
                print(f"  ⚠ Balance {final_bal_num} ≤ 200, skip transfer", flush=True)

            cookies_ok = 1

        except Exception as e:
            print(f"[{session_id}] ❌ Exception: {e}", flush=True)
        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                context.close()
            except Exception:
                pass

    return total, ok, fail, cookies_ok


def main():
    print("=" * 60)
    print("FB Sam loc reward bot v9 — FAST MODE (40 claims → transfer)")
    print("=" * 60)
    print(f"Config: MAX_CLAIMS={MAX_CYCLES} COOLDOWN={DELAY}s REST={REST}s "
          f"TRANSFER_DEST={TRANSFER_DEST_ID}", flush=True)
    print("=" * 60)

    fb_cookies = load_single_cookie_set(SINGLE_COOKIE_FILE)
    if not fb_cookies:
        print("No valid cookie file found. Exiting.", flush=True)
        sys.exit(1)

    global_start = time.time()
    session_id = 0
    grand_total = 0
    grand_ok = 0
    grand_fail = 0

    with sync_playwright() as p:
        while True:
            elapsed = time.time() - global_start
            if elapsed > MAX_RUNTIME:
                print(f"\n⏰ Max runtime ({MAX_RUNTIME}s) reached. Stopping.", flush=True)
                break

            session_id += 1
            print(f"\n{'=' * 60}")
            print(f"[Session {session_id}] Starting at {time.strftime('%H:%M:%S')}", flush=True)
            print(f"{'=' * 60}")

            total, ok, fail, cookies_ok = run_one_session(p, fb_cookies, session_id, global_start)
            grand_total += total
            grand_ok += ok
            grand_fail += fail

            print(f"\n[Session {session_id}] Result: {ok}/{total} claims OK, {fail} fail", flush=True)
            print(f"[Total] {grand_ok}/{grand_total} claims OK", flush=True)

            elapsed = time.time() - global_start
            remaining = max(0, MAX_RUNTIME - int(elapsed))
            print(f"[Time] {int(elapsed)}s elapsed, {remaining}s remaining", flush=True)

            if elapsed < MAX_RUNTIME:
                print(f"[Rest] Sleeping {REST}s before next session...", flush=True)
                time.sleep(REST)

    print(f"\n{'=' * 60}")
    print(f"TỔNG: {session_id} sessions | {grand_ok} claim ok | "
          f"{grand_fail} fail | {grand_total} total", flush=True)
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
