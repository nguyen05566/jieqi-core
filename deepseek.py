#!/usr/bin/env python3
"""Sâm Lốc Farmer Bot v9.3

Fix v9.3:
  - Bỏ regex escape \\s+ (gây SyntaxError: missing ) after argument list)
  - Tìm nút Watch trong dialog bằng cách quét MỌI element
    (div, span, ...) — vì nút Watch không phải <button>/<input>
  - In debug chi tiết khi không tìm thấy nút Watch

Flow mỗi session (1 cookie):
  1. Login FB
  2. Open Sâm Lốc
  3. Claim N video rewards (không tạo bàn thật — luôn chọn bet cao nhất)
  4. Vào bàn 'fffff' + nhập password
  5. Báo sâm → thua → xu chuyển sang Hub
  6. Đóng browser, nghỉ REST, sang cookie kế
"""
import os, sys, time, glob, re, http.cookies

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

# ============ CONFIG ============
SAM_LOC_URL = "https://www.facebook.com/gaming/play/sam_loc_vh"
TARGET_TABLE_NAME = "fffff"
TABLE_PASSWORD = "1"
MAX_CLAIMS = int(os.environ.get("MAX_CLAIMS", "10"))
MAX_FAILS = int(os.environ.get("MAX_FAILS", "5"))
DELAY = float(os.environ.get("COOLDOWN", "3"))
REST = int(os.environ.get("REST_BETWEEN_RUNS", "60"))
MAX_RUNTIME = int(os.environ.get("MAX_RUNTIME", str(330 * 60)))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"
CYCLES = int(os.environ.get("CYCLES", "1"))
SKIP_CLAIM = os.environ.get("SKIP_CLAIM", "false").lower() == "true"


# ============================================================
# COOKIE
# ============================================================
def load_all_cookie_sets(folder="."):
    pattern = os.path.join(folder, "ck*.txt")
    files = glob.glob(pattern)

    def sort_key(path):
        m2 = re.search(r'ck(\d+)\.txt$', os.path.basename(path))
        return int(m2.group(1)) if m2 else 999999

    files.sort(key=sort_key)

    cookie_sets = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
            if not content:
                print(f"[COOKIE] {path} rỗng, bỏ qua", flush=True)
                continue
            content = content.strip('"').strip("'")
            content = " ".join(content.split())
            content = content.replace(";  ", "; ").replace(" ;", ";")
            cookie_sets.append({"file": os.path.basename(path), "raw": content})
            print(f"[COOKIE] Nạp {os.path.basename(path)} "
                  f"({len(content)} ký tự)", flush=True)
        except Exception as e:
            print(f"[COOKIE] Lỗi đọc {path}: {e}", flush=True)

    return cookie_sets


def parse_cookies(raw: str):
    raw = raw.strip().strip('"').strip("'")
    raw = " ".join(raw.split())
    raw = raw.replace(";  ", "; ").replace(" ;", ";")

    if m is not None and hasattr(m, "parse_cookie_header"):
        try:
            return m.parse_cookie_header(raw)
        except Exception:
            pass

    parsed = http.cookies.SimpleCookie()
    parsed.load(raw)
    return [
        {"name": n, "value": v.value, "domain": ".facebook.com",
         "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
        for n, v in parsed.items() if n and v.value
    ]


# ============================================================
# HELPERS
# ============================================================
def parse_balance_to_int(s):
    if s is None:
        return 0
    s = str(s).replace(',', '').replace('.', '').strip()
    if s.endswith('k') or s.endswith('K'):
        try:
            return int(float(s[:-1]) * 1000)
        except Exception:
            return 0
    try:
        return int(s)
    except Exception:
        return 0


def get_bal(gf):
    try:
        return gf.evaluate(
            "() => document.querySelector('.chipBalance')?.textContent.trim() || '?'"
        )
    except Exception:
        return "?"


def get_vi(gf):
    try:
        return gf.evaluate("() => window.Ads?.RewardedVideo?.videoIndex")
    except Exception:
        return None


def find_gf(page, max_wait=120):
    for _ in range(max_wait // 5):
        for f in page.frames:
            if "instant-bundle" in f.url:
                return f
        time.sleep(5)
    return None


# ============================================================
# OPEN GAME
# ============================================================
def open_sam_loc(page, label=""):
    print(f"[{label}] Open Sâm Lốc...", flush=True)
    page.goto(SAM_LOC_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(30000)

    gf = None
    for check_round in range(15):
        if page.locator('input[placeholder="Email or phone"]').count() > 0:
            print(f"[{label}] Cookies expired — login form!", flush=True)
            return None, False
        for f in page.frames:
            if "instant-bundle" in f.url:
                gf = f
                break
        if gf:
            print(f"[{label}] Game frame found (round {check_round+1})", flush=True)
            break
        page.wait_for_timeout(15000)

    if not gf:
        print(f"[{label}] No game frame after 15 rounds", flush=True)
        print(f"[{label}] --- DEBUG frames ---", flush=True)
        for f in page.frames:
            print(f"    {f.url[:140]}", flush=True)
        print(f"[{label}] --- page URL: {page.url}", flush=True)
        try:
            page.screenshot(path="/tmp/farmer_game_load_failed.png",
                            full_page=False)
            print(f"[{label}] --- screenshot saved", flush=True)
        except Exception as e:
            print(f"[{label}] --- screenshot fail: {e}", flush=True)
        return None, False

    page.wait_for_timeout(20000)

    for attempt in range(5):
        try:
            ws_state = gf.evaluate(
                "() => ({ready: window.connection?.ws?.readyState, "
                "hasConn: typeof window.connection !== 'undefined'})"
            )
            if ws_state.get('ready') == 1:
                print(f"[{label}] WS CONNECTED (attempt {attempt+1})", flush=True)
                return gf, True
            gf.evaluate("""() => {
                const btns = document.querySelectorAll(
                    'input[type="button"], button, a');
                for (const b of btns) {
                    if (b.offsetParent === null) continue;
                    const t = (b.value || b.textContent || '')
                        .toLowerCase().trim();
                    if (t === 'reconnect' || t.indexOf('kết nối lại') >= 0) {
                        b.click();
                        return;
                    }
                }
            }""")
            print(f"[{label}] WS retry {attempt+1}/5 "
                  f"(ready={ws_state.get('ready')})", flush=True)
            time.sleep(10)
        except Exception as e:
            print(f"[{label}] WS check error: {e}", flush=True)
            time.sleep(5)

    print(f"[{label}] WS failed, reloading...", flush=True)
    try:
        page.reload(wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(40000)
        for f in page.frames:
            if "instant-bundle" in f.url:
                gf = f
                break
        page.wait_for_timeout(20000)
        for attempt in range(3):
            try:
                if gf.evaluate("() => window.connection?.ws?.readyState === 1"):
                    print(f"[{label}] WS CONNECTED after reload", flush=True)
                    return gf, True
            except Exception:
                pass
            time.sleep(10)
    except Exception:
        pass

    return gf, False


# ============================================================
# CLAIM VIDEO REWARDS
# ============================================================
def _cancel_form(gf):
    try:
        gf.evaluate("""() => {
            const btns = document.querySelectorAll(
                'input[type="button"], button, a');
            for (const b of btns) {
                if (b.offsetParent === null) continue;
                const t = (b.value || b.textContent || '')
                    .toLowerCase().trim();
                if (t === 'cancel' || t === 'huỷ' || t === 'hủy' ||
                    t === 'close' || t === 'đóng' || t === 'back') {
                    b.click();
                    return true;
                }
            }
            return false;
        }""")
    except Exception:
        pass


def _try_cancel_table(gf):
    try:
        result = gf.evaluate("""() => {
            if (typeof cancelTable === 'function') {
                try { cancelTable(); return 'cancelTable()'; }
                catch (e) { return 'err: ' + e; }
            }
            if (typeof leaveTable === 'function') {
                try { leaveTable(); return 'leaveTable()'; }
                catch (e) { return 'err: ' + e; }
            }
            return null;
        }""")
        if result:
            print(f"  [CANCEL] {result}", flush=True)
            time.sleep(2)
            return True
    except Exception:
        pass

    try:
        clicked = gf.evaluate("""() => {
            const btns = document.querySelectorAll(
                'input[type="button"], button, a');
            for (const b of btns) {
                if (b.offsetParent === null) continue;
                const t = (b.value || b.textContent || '')
                    .toLowerCase().trim();
                if (t === 'leave' || t === 'thoát' || t === 'rời' ||
                    t.indexOf('leave table') >= 0 ||
                    t.indexOf('rời bàn') >= 0) {
                    b.click();
                    return t;
                }
            }
            return null;
        }""")
        if clicked:
            print(f"  [CANCEL] Clicked: {clicked}", flush=True)
            time.sleep(2)
            return True
    except Exception:
        pass

    _cancel_form(gf)
    return False


def _normalize_text(s):
    """Chuẩn hoá text trong Python (không dùng regex escape trong JS)."""
    return " ".join(str(s).split())


def claim_video_rewards(gf, max_claims=10):
    """
    Claim VIDEO_REWARD. Luôn chọn bet cao nhất để server trả dialog
    'not enough coin' → không tạo bàn thật.
    Tìm nút Watch trong dialog bằng cách quét MỌI element.
    """
    print(f"\n[FARMER] Claiming {max_claims} video rewards...", flush=True)
    total = 0
    rewards = []
    fails = 0
    highest_bet_seen = None

    for i in range(max_claims):
        try:
            try:
                gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
            except Exception:
                pass
            time.sleep(1)

            # Mở form tạo bàn
            try:
                gf.evaluate("createTable()")
            except Exception:
                pass
            time.sleep(2)

            # Chọn bet cao nhất (radio cuối) — KHÔNG dùng regex escape
            picked = gf.evaluate("""() => {
                const radios = document.querySelectorAll(
                    'input[type="radio"][name="betAmt"]');
                if (!radios || radios.length === 0) {
                    return {ok: false, reason: 'no radios'};
                }
                const last = radios[radios.length - 1];
                last.checked = true;
                last.dispatchEvent(new Event('change', {bubbles: true}));

                function toInt(v) {
                    const s = String(v || '');
                    let out = '';
                    for (let k = 0; k < s.length; k++) {
                        const c = s.charCodeAt(k);
                        if (c >= 48 && c <= 57) out += s[k];
                    }
                    return parseInt(out) || 0;
                }

                const val = toInt(last.value);
                const allLevels = [];
                for (let k = 0; k < radios.length; k++) {
                    allLevels.push(toInt(radios[k].value));
                }
                return {ok: true, picked: val, levels: allLevels};
            }""")

            if not picked.get('ok'):
                print(f"  {i+1:3d}: Không có radio betAmt", flush=True)
                fails += 1
                if fails >= MAX_FAILS:
                    break
                time.sleep(DELAY)
                continue

            bet_val = picked.get('picked', 0)
            levels = picked.get('levels', [])
            if highest_bet_seen is None:
                highest_bet_seen = bet_val
                print(f"  [INFO] Mức cược cao nhất: {bet_val} "
                      f"(các mức: {levels})", flush=True)

            time.sleep(0.5)
            try:
                gf.evaluate("""() => {
                    const b = document.querySelector('input[name="CREATE"]');
                    if (b) b.click();
                }""")
            except Exception:
                pass
            time.sleep(3)

            # ==== Tìm dialog + nút Watch — QUÉT MỌI ELEMENT ====
            # Không dùng regex escape, dùng indexOf và split
            dialog_state = gf.evaluate("""() => {
                function cleanText(s) {
                    return String(s || '').split(' ').filter(function(p) {
                        return p.length > 0;
                    }).join(' ');
                }

                const ds = document.querySelectorAll(
                    '[class*="msgBox"], [class*="dialog"], [class*="Dialog"]');
                for (let di = 0; di < ds.length; di++) {
                    const d = ds[di];
                    if (d.offsetParent === null) continue;
                    const txt = cleanText(d.textContent).toLowerCase();

                    const hasEnough = txt.indexOf('enough coin') >= 0 ||
                                      txt.indexOf('không đủ') >= 0 ||
                                      txt.indexOf('khong du') >= 0 ||
                                      txt.indexOf('not enough') >= 0 ||
                                      txt.indexOf('watch') >= 0 ||
                                      txt.indexOf('xem video') >= 0 ||
                                      txt.indexOf('xem quảng cáo') >= 0;
                    if (!hasEnough) continue;

                    const allEls = d.querySelectorAll('*');
                    const debugList = [];
                    let watchClicked = null;

                    for (let k = 0; k < allEls.length; k++) {
                        const el = allEls[k];
                        if (el.offsetParent === null) continue;

                        const elText = cleanText(el.textContent).trim();
                        const elVal = String(el.value || '').trim();
                        const elTitle = String(el.title || '').trim();
                        const elAria = String(el.getAttribute('aria-label') || '').trim();
                        const elCls = String(el.className || '').toLowerCase();
                        const combined = (elText + ' ' + elVal + ' ' +
                                          elTitle + ' ' + elAria).toLowerCase();

                        if (el.children.length === 0 && elText.length > 0 &&
                            elText.length < 60) {
                            debugList.push({
                                tag: el.tagName,
                                text: elText.substring(0, 40),
                                cls: elCls.substring(0, 40)
                            });
                        }

                        if (el.children.length > 3) continue;

                        const isWatch = combined.indexOf('watch') >= 0 ||
                                        combined.indexOf('xem video') >= 0 ||
                                        combined.indexOf('xem quảng cáo') >= 0 ||
                                        combined.indexOf('xem quang cao') >= 0 ||
                                        combined.indexOf('nhận thưởng') >= 0 ||
                                        combined.indexOf('nhan thuong') >= 0 ||
                                        elCls.indexOf('watch') >= 0;

                        if (!isWatch) continue;

                        if (el.children.length === 0 ||
                            el.tagName === 'BUTTON' ||
                            el.tagName === 'INPUT' ||
                            el.tagName === 'A') {
                            try {
                                el.click();
                                watchClicked = {
                                    tag: el.tagName,
                                    text: elText.substring(0, 40),
                                    cls: elCls.substring(0, 40)
                                };
                                break;
                            } catch (e) {
                                // thử element tiếp
                            }
                        }
                    }

                    if (watchClicked) {
                        return {
                            dialog: true,
                            watch_clicked: true,
                            clicked: watchClicked
                        };
                    }
                    return {
                        dialog: true,
                        watch_clicked: false,
                        snippet: txt.substring(0, 250),
                        debug: debugList.slice(0, 30)
                    };
                }
                return {dialog: false};
            }""")

            if not dialog_state.get('dialog'):
                print(f"  {i+1:3d}: ⚠️ Không có dialog 'not enough coin' "
                      f"→ balance có thể ≥ {bet_val}, huỷ bàn", flush=True)
                _try_cancel_table(gf)
                fails += 1
                if fails >= MAX_FAILS:
                    break
                time.sleep(DELAY)
                continue

            if not dialog_state.get('watch_clicked'):
                print(f"  {i+1:3d}: Dialog hiện, KHÔNG có nút Watch. "
                      f"Debug:", flush=True)
                snip = dialog_state.get('snippet', '')
                print(f"      Snippet: {snip[:200]}", flush=True)
                for d in dialog_state.get('debug', [])[:25]:
                    print(f"      [{d.get('tag', ''):6s}] "
                          f"'{d.get('text', '')[:45]}' "
                          f"cls='{d.get('cls', '')[:30]}'", flush=True)
                fails += 1
                if fails >= MAX_FAILS:
                    break
                time.sleep(DELAY)
                continue

            print(f"  {i+1:3d}: Clicked Watch: {dialog_state.get('clicked')}",
                  flush=True)
            time.sleep(1)

            # Gửi WS VIDEO_REWARD
            result = gf.evaluate("""() => {
                return new Promise((resolve) => {
                    try {
                        if (!window.connection || !connection.ws ||
                            connection.ws.readyState !== 1) {
                            resolve({success: false,
                                     error: 'ws not connected'});
                            return;
                        }
                        const msg = new OutboundMessage("VIDEO_REWARD");
                        msg.writeByte(1);
                        let r = false;
                        connection.send(msg, function(resp, ok) {
                            if (r) return;
                            r = true;
                            if (ok) {
                                try {
                                    const a = resp.readLong();
                                    if (window.Ads && window.Ads.RewardedVideo) {
                                        window.Ads.RewardedVideo.videoIndex++;
                                        if (window.Ads.RewardedVideo.updateRewardButton)
                                            window.Ads.RewardedVideo.updateRewardButton();
                                    }
                                    resolve({success: true, amount: a});
                                } catch (e) {
                                    resolve({success: true, amount: 0,
                                             error: e.toString()});
                                }
                            } else {
                                resolve({success: false,
                                         error: 'no response'});
                            }
                        });
                        setTimeout(() => {
                            if (!r) {
                                r = true;
                                resolve({success: false, error: 'timeout'});
                            }
                        }, 8000);
                    } catch (e) {
                        resolve({success: false, error: e.toString()});
                    }
                });
            }""")

            if result.get('success') and result.get('amount', 0) > 0:
                amount = result['amount']
                total += amount
                rewards.append(amount)
                fails = 0
                time.sleep(1)
                bal = get_bal(gf)
                vi = get_vi(gf)
                print(f"  {i+1:3d}: +{amount:4d} | {bal:8s} | vi={vi} | "
                      f"total={total:6d}", flush=True)
            else:
                fails += 1
                print(f"  {i+1:3d}: FAIL ({result.get('error', '')}) | "
                      f"fails={fails}", flush=True)
                try:
                    vi = get_vi(gf)
                    if vi and vi >= 7:
                        print(f"  Quota hết (vi={vi}) → dừng", flush=True)
                        break
                except Exception:
                    pass
                if fails >= MAX_FAILS:
                    print("  Dừng claim — quá nhiều fail", flush=True)
                    break

            try:
                gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
            except Exception:
                pass

            time.sleep(DELAY)

        except Exception as e:
            print(f"  {i+1:3d}: ERROR ({e})", flush=True)
            fails += 1
            if fails >= MAX_FAILS:
                break
            time.sleep(DELAY)

    print(f"[FARMER] Claims done: {len(rewards)} ok, +{total} coin", flush=True)
    return total, rewards


# ============================================================
# FIND + JOIN TABLE — bản sửa không dùng regex escape
# ============================================================
def find_and_join_table(gf, page, table_name, password):
    print(f"\n[FARMER] Looking for table '{table_name}'...", flush=True)

    try:
        gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
    except Exception:
        pass
    time.sleep(1)

    # Click "Find table"
    clicked = gf.evaluate("""() => {
        function cleanText(s) {
            return String(s || '').split(' ').filter(function(p) {
                return p.length > 0;
            }).join(' ');
        }
        const all = document.querySelectorAll(
            'a, button, input[type="button"], [role="button"], ' +
            '[onclick], [class*="btn"], div, span');
        for (let k = 0; k < all.length; k++) {
            const el = all[k];
            if (el.offsetParent === null) continue;
            if (el.children.length > 2) continue;
            const txt = cleanText(el.textContent || el.value || '')
                .trim().toLowerCase();
            if (txt === 'find table' || txt === 'tìm bàn' ||
                txt.indexOf('find table') >= 0 ||
                txt.indexOf('tìm bàn') >= 0) {
                el.click();
                return {clicked: true, text: txt, tag: el.tagName};
            }
        }
        return {clicked: false};
    }""")
    print(f"  Clicked Find table: {clicked}", flush=True)
    time.sleep(3)

    # Cuộn lên đầu
    gf.evaluate("""() => {
        const cs = document.querySelectorAll(
            '[class*="list"], [class*="table"], [class*="lobby"], ' +
            '[class*="content"], [class*="scroll"], [class*="room"]');
        for (let k = 0; k < cs.length; k++) {
            const c = cs[k];
            if (c.scrollHeight > c.clientHeight) c.scrollTop = 0;
        }
    }""")
    time.sleep(2)

    # Tìm Nam Quan roomCard
    nam_quan_clicked = False
    for scroll_round in range(30):
        nam_quan_pos = gf.evaluate("""() => {
            function cleanText(s) {
                return String(s || '').split(' ').filter(function(p) {
                    return p.length > 0;
                }).join(' ');
            }
            const cards = document.querySelectorAll(
                'a.roomCard, [class*="roomCard"]');
            for (let k = 0; k < cards.length; k++) {
                const el = cards[k];
                if (el.offsetParent === null) continue;
                const txt = cleanText(el.textContent).trim().toLowerCase();
                if (txt.indexOf('nam quan') === 0 || txt === 'nam quan') {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 20 && rect.height > 10) {
                        return {found: true,
                                x: Math.round(rect.x + rect.width/2),
                                y: Math.round(rect.y + rect.height/2)};
                    }
                }
            }
            return {found: false};
        }""")
        if nam_quan_pos.get('found'):
            try:
                frame = None
                for f in page.frames:
                    if "instant-bundle" in f.url:
                        frame = f
                        break
                if frame:
                    frame_rect = frame.evaluate("""() => {
                        const r = window.frameElement
                            ? window.frameElement.getBoundingClientRect()
                            : {x: 0, y: 0};
                        return {x: r.x, y: r.y};
                    }""")
                    abs_x = nam_quan_pos['x'] + frame_rect.get('x', 0)
                    abs_y = nam_quan_pos['y'] + frame_rect.get('y', 0)
                    page.mouse.click(abs_x, abs_y)
                    time.sleep(5)
                    nam_quan_clicked = True
            except Exception as e:
                print(f"  Mouse click error: {e}", flush=True)
            break

        gf.evaluate("""() => {
            const cs = document.querySelectorAll(
                '[class*="list"], [class*="table"], [class*="lobby"], ' +
                '[class*="content"], [class*="scroll"], [class*="room"]');
            for (let k = 0; k < cs.length; k++) {
                const c = cs[k];
                if (c.scrollHeight > c.clientHeight) c.scrollTop += 150;
            }
        }""")
        time.sleep(0.5)

    print(f"  Nam Quan clicked: {nam_quan_clicked}", flush=True)
    time.sleep(3)

    # Search bàn 'fffff'
    for tab_name in ['all', 'available', 'waiting']:
        gf.evaluate("""(tabName) => {
            function cleanText(s) {
                return String(s || '').split(' ').filter(function(p) {
                    return p.length > 0;
                }).join(' ');
            }
            const all = document.querySelectorAll(
                'a, button, input[type="button"], [role="button"], ' +
                '[class*="btn"], div, span');
            for (let k = 0; k < all.length; k++) {
                const el = all[k];
                if (el.offsetParent === null) continue;
                if (el.children.length > 2) continue;
                const txt = cleanText(el.textContent || el.value || '')
                    .trim().toLowerCase();
                if (txt === tabName ||
                    (txt.length < 15 && txt.indexOf(tabName) >= 0)) {
                    el.click();
                    return;
                }
            }
        }""", tab_name)
        time.sleep(3)

        for _ in range(10):
            gf.evaluate("""() => {
                const cs = document.querySelectorAll(
                    '[class*="list"], [class*="table"], ' +
                    '[class*="lobby"], [class*="content"]');
                for (let k = 0; k < cs.length; k++) {
                    const c = cs[k];
                    if (c.scrollHeight > c.clientHeight)
                        c.scrollTop = c.scrollHeight;
                }
                window.scrollTo(0, document.body.scrollHeight);
            }""")
            time.sleep(1)

        found_check = gf.evaluate("""(targetName) => {
            function cleanText(s) {
                return String(s || '').split(' ').filter(function(p) {
                    return p.length > 0;
                }).join(' ');
            }
            const all = document.querySelectorAll('*');
            const lt = String(targetName).toLowerCase();
            for (let k = 0; k < all.length; k++) {
                const el = all[k];
                if (el.offsetParent === null) continue;
                if (el.children.length > 5) continue;
                const txt = cleanText(el.textContent).trim();
                if (txt.length > 0 && txt.length < 80 &&
                    txt.toLowerCase().indexOf(lt) >= 0) {
                    return {found: true, text: txt.substring(0, 60)};
                }
            }
            return {found: false};
        }""", table_name)
        if found_check.get('found'):
            print(f"  ✓ Found '{table_name}' in '{tab_name}'", flush=True)
            break

    # Click bàn
    clicked_table = gf.evaluate("""(targetName) => {
        function cleanText(s) {
            return String(s || '').split(' ').filter(function(p) {
                return p.length > 0;
            }).join(' ');
        }
        const all = document.querySelectorAll('*');
        const lt = String(targetName).toLowerCase();
        const candidates = [];
        for (let k = 0; k < all.length; k++) {
            const el = all[k];
            if (el.offsetParent === null) continue;
            if (el.children.length > 5) continue;
            const txt = cleanText(el.textContent).trim();
            if (txt.length > 0 && txt.length < 80 &&
                txt.toLowerCase().indexOf(lt) >= 0) {
                candidates.push(el);
            }
        }
        if (candidates.length > 0) {
            try {
                candidates[0].click();
                return {clicked: true,
                        text: cleanText(candidates[0].textContent)
                            .trim().substring(0, 60)};
            } catch (e) {
                return {clicked: false, error: e.toString()};
            }
        }
        return null;
    }""", table_name)
    print(f"  Clicked table: {clicked_table}", flush=True)
    time.sleep(5)

    # Nhập password
    has_password_input = gf.evaluate("""() => {
        const dialog = document.querySelector(
            '.msgBoxBackGround, [class*="msgBox"], ' +
            '[class*="dialog"], [class*="Dialog"]');
        if (!dialog) return {found: false};
        const inputs = dialog.querySelectorAll(
            'input[type="password"], input[type="text"]');
        return {found: inputs.length > 0, count: inputs.length};
    }""")
    print(f"  Password input: {has_password_input}", flush=True)

    if has_password_input.get('found'):
        pw_entered = gf.evaluate("""(pw) => {
            const dialog = document.querySelector(
                '.msgBoxBackGround, [class*="msgBox"], ' +
                '[class*="dialog"], [class*="Dialog"]');
            if (!dialog) return {entered: false};
            let inputs = dialog.querySelectorAll('input[type="password"]');
            if (inputs.length === 0) {
                inputs = dialog.querySelectorAll('input[type="text"]');
            }
            for (let k = 0; k < inputs.length; k++) {
                const inp = inputs[k];
                if (inp.offsetParent === null) continue;
                inp.value = pw;
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                return {entered: true};
            }
            return {entered: false};
        }""", password)
        print(f"  Password entered: {pw_entered}", flush=True)
        time.sleep(1)

    # Click Play
    play_clicked = None
    for play_attempt in range(3):
        play_clicked = gf.evaluate("""() => {
            function cleanText(s) {
                return String(s || '').split(' ').filter(function(p) {
                    return p.length > 0;
                }).join(' ');
            }
            const all = document.querySelectorAll(
                'input[type="button"], button, a, ' +
                '[role="button"], [class*="btn"]');
            for (let k = 0; k < all.length; k++) {
                const b = all[k];
                if (b.offsetParent === null) continue;
                const txt = cleanText(b.value || b.textContent || '')
                    .toLowerCase().trim();
                if (txt === 'play' || txt === 'vào' ||
                    txt === 'join' || txt === 'vào bàn') {
                    b.click();
                    return {clicked: true, text: txt};
                }
            }
            return {clicked: false};
        }""")
        if play_clicked.get('clicked'):
            break
        time.sleep(2)
    print(f"  Clicked Play: {play_clicked}", flush=True)
    time.sleep(3)

    # Dialog password sau Play
    post_play_dialog = []
    for check in range(8):
        post_play_dialog = gf.evaluate("""() => {
            const result = [];
            const inputs = document.querySelectorAll('input[type="password"]');
            for (let k = 0; k < inputs.length; k++) {
                const inp = inputs[k];
                if (inp.offsetParent === null) continue;
                result.push({found: true, name: inp.name || ''});
            }
            return result;
        }""")
        if post_play_dialog:
            print(f"  Password dialog after Play (check {check+1})", flush=True)
            break
        time.sleep(2)

    if post_play_dialog:
        gf.evaluate("""(pw) => {
            const inputs = document.querySelectorAll('input[type="password"]');
            for (let k = 0; k < inputs.length; k++) {
                const inp = inputs[k];
                if (inp.offsetParent === null) continue;
                inp.focus();
                inp.value = pw;
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                return;
            }
        }""", password)
        time.sleep(2)

        gf.evaluate("""() => {
            const inputs = document.querySelectorAll('input[type="password"]');
            for (let k = 0; k < inputs.length; k++) {
                const inp = inputs[k];
                if (inp.offsetParent === null) continue;
                let dialog = inp.parentElement;
                for (let i = 0; i < 10 && dialog; i++) {
                    if (dialog.querySelector('input[type="button"], button'))
                        break;
                    dialog = dialog.parentElement;
                }
                if (dialog) {
                    const btns = dialog.querySelectorAll(
                        'input[type="button"], button');
                    for (let j = 0; j < btns.length; j++) {
                        const b = btns[j];
                        if (b.offsetParent === null) continue;
                        const txt = String(b.value || b.textContent || '')
                            .toLowerCase().trim();
                        if (txt === 'ok' || txt === 'xác nhận' ||
                            txt === 'confirm') {
                            b.click();
                            return;
                        }
                    }
                    for (let j = 0; j < btns.length; j++) {
                        if (btns[j].offsetParent !== null) {
                            btns[j].click();
                            return;
                        }
                    }
                }
            }
        }""")
        print(f"  Password + OK clicked", flush=True)

    # Đợi vào bàn
    for wait_round in range(4):
        wait_time = 15 if wait_round == 0 else 10
        time.sleep(wait_time)

        try:
            page.screenshot(
                path=f"/tmp/farmer_after_pw_r{wait_round+1}.png",
                full_page=True
            )
        except Exception:
            pass

        in_table = gf.evaluate("""() => {
            const hasBoard = document.querySelector(
                '.tableBoard, .gameBoard, [class*="tableBoard"], ' +
                '[class*="game-board"]') !== null;
            let hasBaoSam = false;
            let hasLeaveBtn = false;
            let hasDealBtn = false;
            const btns = document.querySelectorAll(
                'input[type="button"], button, a, [class*="btn"]');
            for (let k = 0; k < btns.length; k++) {
                const b = btns[k];
                if (b.offsetParent === null) continue;
                const t = String(b.value || b.textContent || '').toLowerCase();
                if (t.indexOf('báo sâm') >= 0 || t.indexOf('bao sam') >= 0 ||
                    t.indexOf('declare') >= 0 || t.indexOf('invade') >= 0)
                    hasBaoSam = true;
                if (t.indexOf('rời') >= 0 || t.indexOf('leave') >= 0 ||
                    t.indexOf('thoát') >= 0) hasLeaveBtn = true;
                if (t.indexOf('deal') >= 0 || t.indexOf('chia') >= 0)
                    hasDealBtn = true;
            }
            return {hasBoard, hasBaoSam, hasLeaveBtn, hasDealBtn};
        }""")

        print(f"  Round {wait_round+1}: board={in_table.get('hasBoard')} "
              f"baoSam={in_table.get('hasBaoSam')} "
              f"leave={in_table.get('hasLeaveBtn')}", flush=True)

        if (in_table.get('hasBoard') or in_table.get('hasBaoSam') or
            in_table.get('hasLeaveBtn') or in_table.get('hasDealBtn')):
            print(f"  ✓ IN TABLE", flush=True)
            return True

    if post_play_dialog:
        print(f"  Password accepted → assume in table", flush=True)
        return True

    print(f"  Could not confirm in-table", flush=True)
    return False


# ============================================================
# DECLARE SÂM
# ============================================================
def declare_sam_and_wait(gf, max_wait=240):
    print(f"\n[FARMER] Declaring Sâm + waiting (max {max_wait}s)...", flush=True)

    declared = gf.evaluate("""() => {
        function cleanText(s) {
            return String(s || '').split(' ').filter(function(p) {
                return p.length > 0;
            }).join(' ');
        }
        const all = document.querySelectorAll('*');
        for (let k = 0; k < all.length; k++) {
            const el = all[k];
            if (el.offsetParent === null) continue;
            const txt = cleanText(el.textContent || el.value || '')
                .toLowerCase().trim();
            const title = String(el.getAttribute('title') ||
                                 el.getAttribute('aria-label') || '')
                .toLowerCase();
            const cls = String(el.className || '').toLowerCase();
            if (txt === 'invade' ||
                txt.indexOf('báo sâm') >= 0 || txt.indexOf('bao sam') >= 0 ||
                title === 'invade' || title.indexOf('báo sâm') >= 0 ||
                cls.indexOf('invade') >= 0 || cls.indexOf('baosam') >= 0) {
                el.click();
                return {declared: true, tag: el.tagName, text: txt};
            }
        }
        return {declared: false};
    }""")
    print(f"  Clicked Invade/Báo sâm: {declared}", flush=True)

    start = time.time()
    last_balance = None
    game_over_detected = False

    while time.time() - start < max_wait:
        try:
            state = gf.evaluate("""() => {
                const txt = (document.body
                    ? document.body.innerText.substring(0, 800)
                    : '').toLowerCase();
                const gameOver = txt.indexOf('game over') >= 0 ||
                                 txt.indexOf('kết thúc') >= 0 ||
                                 txt.indexOf('kết quả') >= 0 ||
                                 txt.indexOf('you lose') >= 0 ||
                                 txt.indexOf('thua') >= 0 ||
                                 txt.indexOf('winner') >= 0 ||
                                 txt.indexOf('thắng') >= 0;
                let hasOkBtn = false;
                const els = document.querySelectorAll(
                    'input[type="button"], button, a, div, span');
                for (let k = 0; k < els.length; k++) {
                    const b = els[k];
                    if (b.offsetParent === null) continue;
                    const t = String(b.value || b.textContent || '')
                        .toLowerCase().trim();
                    if (t === 'ok' || t === 'đóng' || t === 'close' ||
                        t === 'tiếp tục') { hasOkBtn = true; break; }
                }
                const balEl = document.querySelector('.chipBalance');
                const balance = balEl ? balEl.textContent.trim() : null;
                return {gameOver, hasOkBtn, balance};
            }""")

            if state.get('gameOver') or state.get('hasOkBtn'):
                print(f"  ✓ Game over detected", flush=True)
                gf.evaluate("""() => {
                    const btns = document.querySelectorAll(
                        'input[type="button"], button, a, div, span');
                    for (let k = 0; k < btns.length; k++) {
                        const b = btns[k];
                        if (b.offsetParent === null) continue;
                        const t = String(b.value || b.textContent || '')
                            .toLowerCase().trim();
                        if (t === 'ok' || t === 'đóng' || t === 'close' ||
                            t === 'tiếp tục' || t.indexOf('chơi lại') >= 0) {
                            b.click();
                            return;
                        }
                    }
                }""")
                time.sleep(2)
                game_over_detected = True
                break

            current_bal = state.get('balance')
            if current_bal and current_bal != last_balance:
                print(f"  [{int(time.time()-start)}s] Balance: {current_bal}",
                      flush=True)
                last_balance = current_bal

        except Exception as e:
            print(f"  State check error: {e}", flush=True)
        time.sleep(5)

    try:
        final_bal = gf.evaluate(
            "() => document.querySelector('.chipBalance')?.textContent.trim() || '?'"
        )
        print(f"  Final balance: {final_bal}", flush=True)
    except Exception:
        pass

    return game_over_detected


# ============================================================
# RUN ONE SESSION
# ============================================================
def run_one_session(p, fb_cookies, session_id, started_at, cookie_file="?"):
    print(f"\n########## SESSION {session_id} [{cookie_file}] ##########", flush=True)

    browser = p.chromium.launch(
        headless=HEADLESS,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled",
              "--disable-gpu"],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        locale="en-US",
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

    print("[1] Login FB...", flush=True)
    try:
        page.goto("https://www.facebook.com/",
                  wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  ERROR goto: {e}", flush=True)
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False

    page.wait_for_timeout(5000)

    if page.locator('input[placeholder="Email or phone"]').count() > 0:
        print("  ERROR: Not logged in", flush=True)
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, False
    print("  OK", flush=True)

    gf, ws_ok = open_sam_loc(page, f"S{session_id}")
    if not ws_ok or gf is None:
        print(f"[SESSION {session_id}] Không mở được game", flush=True)
        try:
            browser.close()
        except Exception:
            pass
        return 0, 0, 0, True

    bal_initial = get_bal(gf)
    print(f"[SESSION {session_id}] Initial balance: {bal_initial}", flush=True)

    grand_claimed = 0
    grand_lost = 0
    cycle_results = []

    for cycle in range(1, CYCLES + 1):
        if time.time() - started_at > MAX_RUNTIME:
            print(f"[CYCLE {cycle}] Hết thời gian, dừng.", flush=True)
            break

        print(f"\n{'='*60}", flush=True)
        print(f"[SESSION {session_id}] CYCLE {cycle}/{CYCLES}", flush=True)
        print(f"{'='*60}", flush=True)

        cycle_result = {"cycle": cycle, "claimed": 0,
                        "joined": False, "declared": False, "lost_xu": 0}

        if SKIP_CLAIM:
            print(f"\n[CYCLE {cycle}] SKIP claims", flush=True)
            total_claimed, rewards = 0, []
        else:
            print(f"\n[CYCLE {cycle} STEP 1] Claim video rewards", flush=True)
            bal_before = get_bal(gf)
            total_claimed, rewards = claim_video_rewards(gf, MAX_CLAIMS)
            bal_after = get_bal(gf)
            print(f"[CYCLE {cycle}] {bal_before} → {bal_after} "
                  f"(+{total_claimed})", flush=True)
        grand_claimed += total_claimed
        cycle_result["claimed"] = total_claimed

        if time.time() - started_at > MAX_RUNTIME:
            cycle_results.append(cycle_result)
            break

        print(f"\n[CYCLE {cycle} STEP 2] Join table '{TARGET_TABLE_NAME}'",
              flush=True)
        try:
            joined = find_and_join_table(gf, page, TARGET_TABLE_NAME,
                                         TABLE_PASSWORD)
        except Exception as e:
            print(f"[CYCLE {cycle}] Join table error: {e}", flush=True)
            joined = False
        cycle_result["joined"] = joined

        if not joined:
            print(f"[CYCLE {cycle}] Không vào được bàn, skip declare", flush=True)
            cycle_results.append(cycle_result)
            continue

        print(f"\n[CYCLE {cycle} STEP 3] Declare sâm + wait", flush=True)
        bal_before_lose = get_bal(gf)
        print(f"[CYCLE {cycle}] Balance before: {bal_before_lose}", flush=True)
        game_over = declare_sam_and_wait(gf, max_wait=240)
        bal_after_lose = get_bal(gf)
        print(f"[CYCLE {cycle}] Balance after: {bal_after_lose}", flush=True)

        try:
            before = parse_balance_to_int(bal_before_lose)
            after = parse_balance_to_int(bal_after_lose)
            lost = before - after
            if lost > 0:
                grand_lost += lost
                cycle_result["lost_xu"] = lost
                print(f"[CYCLE {cycle}] Lost to Hub: -{lost}", flush=True)
        except Exception:
            pass

        cycle_result["declared"] = game_over
        cycle_results.append(cycle_result)

        try:
            gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
            time.sleep(2)
            gf.evaluate("""() => {
                const btns = document.querySelectorAll(
                    'input[type="button"], button, a');
                for (let k = 0; k < btns.length; k++) {
                    const b = btns[k];
                    if (b.offsetParent === null) continue;
                    const t = String(b.value || b.textContent || '')
                        .toLowerCase();
                    if (t.indexOf('back') >= 0 || t.indexOf('rời') >= 0 ||
                        t.indexOf('thoát') >= 0 || t.indexOf('return') >= 0 ||
                        t.indexOf('lobby') >= 0) {
                        b.click();
                        return;
                    }
                }
            }""")
            time.sleep(5)
        except Exception:
            pass

    bal_final = get_bal(gf)
    print(f"\n[SESSION {session_id}] SUMMARY", flush=True)
    print(f"  Initial:  {bal_initial}", flush=True)
    print(f"  Final:    {bal_final}", flush=True)
    print(f"  Claimed:  +{grand_claimed}", flush=True)
    print(f"  Lost:     -{grand_lost}", flush=True)
    print(f"  Net:      +{grand_claimed - grand_lost}", flush=True)

    print(f"[SESSION {session_id}] Đóng browser...", flush=True)
    try:
        browser.close()
    except Exception:
        pass

    return grand_claimed, len(cycle_results), grand_lost, True


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60, flush=True)
    print("Sâm Lốc Farmer Bot v9.3", flush=True)
    print(f"Table: '{TARGET_TABLE_NAME}' | Password: '{TABLE_PASSWORD}'", flush=True)
    print(f"Claims/cycle: {MAX_CLAIMS} | Cycles: {CYCLES} | "
          f"SKIP_CLAIM={SKIP_CLAIM}", flush=True)
    print(f"DELAY={DELAY}s REST={REST}s MAX_RUNTIME={MAX_RUNTIME}s "
          f"HEADLESS={HEADLESS}", flush=True)
    print("=" * 60, flush=True)

    cookie_sets = load_all_cookie_sets()
    if not cookie_sets:
        print("[STOP] Không có file ck*.txt nào.", flush=True)
        return 1

    print(f"\nTìm thấy {len(cookie_sets)} bộ cookie: "
          f"{[c['file'] for c in cookie_sets]}", flush=True)

    started_at = time.time()
    grand_total_claimed = 0
    grand_total_lost = 0
    session_id = 0
    cookie_idx = 0

    with sync_playwright() as p:
        while True:
            if time.time() - started_at > MAX_RUNTIME:
                print(f"\n[TIME UP] {int(time.time()-started_at)}s", flush=True)
                break

            entry = cookie_sets[cookie_idx % len(cookie_sets)]
            round_no = cookie_idx // len(cookie_sets) + 1
            cookie_idx += 1

            print(f"\n{'='*60}", flush=True)
            print(f">>> FARMER COOKIE: {entry['file']}  |  vòng {round_no}  "
                  f"|  lượt #{cookie_idx}", flush=True)
            print(f"{'='*60}", flush=True)

            fb_cookies = parse_cookies(entry["raw"])
            if not fb_cookies:
                print(f"[WARN] {entry['file']} parse rỗng", flush=True)
                continue

            session_id += 1
            try:
                claimed, cycles_done, lost, cookies_ok = run_one_session(
                    p, fb_cookies, session_id, started_at, entry["file"]
                )
            except Exception as e:
                print(f"[ERROR] session {session_id}: {e}", flush=True)
                claimed, lost, cookies_ok = 0, 0, False

            grand_total_claimed += claimed
            grand_total_lost += lost

            if not cookies_ok:
                print(f"[WARN] Cookie {entry['file']} hết hạn → bỏ qua",
                      flush=True)
                continue

            if time.time() - started_at > MAX_RUNTIME:
                break

            if cookie_idx % len(cookie_sets) == 0:
                print(f"[CYCLE] Hết vòng {round_no} ({len(cookie_sets)} "
                      f"cookie). Nghỉ {REST}s...", flush=True)
                time.sleep(REST)
            else:
                nxt = cookie_sets[cookie_idx % len(cookie_sets)]['file']
                print(f"[REST] Nghỉ {REST}s rồi sang {nxt}...", flush=True)
                time.sleep(REST)

        print("\n" + "=" * 60, flush=True)
        print(f"  TỔNG: {session_id} sessions", flush=True)
        print(f"  Claimed: +{grand_total_claimed} coin", flush=True)
        print(f"  Lost to Hub: -{grand_total_lost} coin", flush=True)
        print(f"  Thời gian: {int(time.time()-started_at)}s", flush=True)
        print("=" * 60, flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
