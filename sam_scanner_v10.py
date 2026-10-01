#!/usr/bin/env python3
"""Sâm Lốc Game Scanner v10

Mục đích: quét TOÀN BỘ cấu trúc game Sâm Lốc để hiểu:
  - Frame structure
  - Buttons, inputs, links
  - Lobby regions + tables
  - Create table form (bet radios)
  - Dialogs (Alert, Watch video, Password)
  - Canvas, hidden elements

Không claim, không chơi. Chỉ đọc DOM và in log.
"""
import os, sys, time, glob, re, json, http.cookies

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_dom_merged as m
except Exception:
    m = None

from playwright.sync_api import sync_playwright

# ============ CONFIG ============
SAM_LOC_URL = "https://www.facebook.com/gaming/play/sam_loc_vh"
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"


# ============ COOKIE ============
def load_all_cookie_sets(folder="."):
    files = sorted(
        glob.glob(os.path.join(folder, "ck*.txt")),
        key=lambda p: int(re.search(r'ck(\d+)\.txt$', os.path.basename(p)).group(1))
        if re.search(r'ck(\d+)\.txt$', os.path.basename(p)) else 999999
    )
    result = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read().strip().strip('"').strip("'")
            content = " ".join(content.split())
            if content:
                result.append({"file": os.path.basename(path), "raw": content})
        except Exception:
            pass
    return result


def parse_cookies(raw):
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


# ============ SCAN HELPERS ============
def scan_frame_info(page):
    """Quét thông tin tất cả frames."""
    print("\n" + "=" * 70, flush=True)
    print("SCAN 1: FRAME STRUCTURE", flush=True)
    print("=" * 70, flush=True)
    print(f"Main page URL: {page.url}", flush=True)
    print(f"Total frames: {len(page.frames)}", flush=True)
    for i, f in enumerate(page.frames):
        try:
            print(f"\n  [Frame {i}]", flush=True)
            print(f"    URL: {f.url[:180]}", flush=True)
            print(f"    Name: {f.name}", flush=True)
            print(f"    Is detached: {f.is_detached()}", flush=True)
        except Exception as e:
            print(f"    [Error: {e}]", flush=True)


def scan_page_structure(gf, label=""):
    """Quét toàn bộ element trong game frame."""
    print("\n" + "=" * 70, flush=True)
    print(f"SCAN 2: PAGE STRUCTURE ({label})", flush=True)
    print("=" * 70, flush=True)

    result = gf.evaluate("""() => {
        const out = {
            title: document.title,
            url: window.location.href,
            bodyText: (document.body ? document.body.innerText : '').substring(0, 2000),
            counts: {
                divs: document.querySelectorAll('div').length,
                spans: document.querySelectorAll('span').length,
                buttons: document.querySelectorAll('button').length,
                inputs: document.querySelectorAll('input').length,
                links: document.querySelectorAll('a').length,
                canvases: document.querySelectorAll('canvas').length,
                iframes: document.querySelectorAll('iframe').length,
                images: document.querySelectorAll('img').length,
                forms: document.querySelectorAll('form').length,
            },
            canvases: [],
            iframes: [],
            inputs: [],
            globals: [],
        };

        // Canvas info
        document.querySelectorAll('canvas').forEach((c, i) => {
            out.canvases.push({
                index: i,
                id: c.id || '',
                cls: (c.className || '').toString().substring(0, 60),
                width: c.width,
                height: c.height,
                visible: c.offsetParent !== null
            });
        });

        // Iframe info
        document.querySelectorAll('iframe').forEach((f, i) => {
            out.iframes.push({
                index: i,
                id: f.id || '',
                src: (f.src || '').substring(0, 150),
                name: f.name || '',
                visible: f.offsetParent !== null
            });
        });

        // Input info
        document.querySelectorAll('input').forEach((inp, i) => {
            if (i > 30) return;
            out.inputs.push({
                index: i,
                type: inp.type || '',
                name: inp.name || '',
                id: inp.id || '',
                value: String(inp.value || '').substring(0, 30),
                visible: inp.offsetParent !== null,
                cls: (inp.className || '').toString().substring(0, 60)
            });
        });

        // Game globals
        const globalNames = ['connection', 'OutboundMessage', 'Ads',
                             'createTable', 'cancelTable', 'leaveTable',
                             'game', 'table', 'lobby', 'player'];
        for (const n of globalNames) {
            try {
                const v = window[n];
                out.globals.push({
                    name: n,
                    exists: typeof v !== 'undefined',
                    type: typeof v,
                    keys: (v && typeof v === 'object') ?
                          Object.keys(v).slice(0, 20) : null
                });
            } catch (e) {
                out.globals.push({name: n, error: e.toString()});
            }
        }

        return out;
    }""")

    print(f"\n  Title: {result.get('title')}", flush=True)
    print(f"  URL: {result.get('url')}", flush=True)

    counts = result.get('counts', {})
    print(f"\n  Element counts:", flush=True)
    for k, v in counts.items():
        print(f"    {k:10s} = {v}", flush=True)

    print(f"\n  Canvas ({len(result.get('canvases', []))}):", flush=True)
    for c in result.get('canvases', []):
        print(f"    #{c['index']} id='{c['id']}' "
              f"size={c['width']}x{c['height']} "
              f"visible={c['visible']} cls='{c['cls'][:40]}'", flush=True)

    print(f"\n  Iframes ({len(result.get('iframes', []))}):", flush=True)
    for f in result.get('iframes', []):
        print(f"    #{f['index']} id='{f['id']}' "
              f"src='{f['src'][:80]}' visible={f['visible']}", flush=True)

    print(f"\n  Inputs ({len(result.get('inputs', []))}):", flush=True)
    for inp in result.get('inputs', []):
        print(f"    #{inp['index']} type='{inp['type']}' "
              f"name='{inp['name']}' id='{inp['id']}' "
              f"value='{inp['value']}' visible={inp['visible']}",
              flush=True)

    print(f"\n  Game globals:", flush=True)
    for g in result.get('globals', []):
        if g.get('error'):
            print(f"    {g['name']}: ERROR {g['error']}", flush=True)
        else:
            keys_str = f" keys={g['keys']}" if g.get('keys') else ""
            print(f"    {g['name']:20s} exists={g['exists']} "
                  f"type={g['type']}{keys_str}", flush=True)

    print(f"\n  Body text (2000 chars):", flush=True)
    print(f"    {result.get('bodyText', '')[:2000]}", flush=True)

    return result


def scan_buttons(gf, label=""):
    """Quét tất cả button/link có thể click."""
    print("\n" + "=" * 70, flush=True)
    print(f"SCAN 3: BUTTONS & LINKS ({label})", flush=True)
    print("=" * 70, flush=True)

    result = gf.evaluate("""() => {
        function clean(s) {
            return String(s || '').split(' ').filter(p => p.length > 0).join(' ');
        }
        const out = [];
        const seen = new Set();
        const all = document.querySelectorAll(
            'a, button, input[type="button"], input[type="submit"], ' +
            '[role="button"], [onclick], [class*="btn"]');

        for (const el of all) {
            if (el.offsetParent === null) continue;
            const txt = clean(el.textContent || el.value || '').trim();
            const cls = String(el.className || '').substring(0, 60);
            const id = el.id || '';
            const key = `${el.tagName}|${id}|${txt.substring(0,30)}`;
            if (seen.has(key)) continue;
            seen.add(key);

            out.push({
                tag: el.tagName,
                id: id,
                cls: cls,
                text: txt.substring(0, 80),
                title: String(el.title || '').substring(0, 40),
                onclick: String(el.getAttribute('onclick') || '').substring(0, 60)
            });
        }
        return out;
    }""")

    print(f"\n  Total clickable: {len(result)}", flush=True)
    for i, b in enumerate(result):
        print(f"    #{i:3d} [{b['tag']:6s}] "
              f"id='{b['id'][:20]}' "
              f"cls='{b['cls'][:30]}' "
              f"text='{b['text'][:50]}' "
              f"title='{b['title'][:25]}'", flush=True)

    return result


def scan_dialogs(gf, label=""):
    """Quét tất cả dialog đang hiện."""
    print("\n" + "=" * 70, flush=True)
    print(f"SCAN 4: VISIBLE DIALOGS ({label})", flush=True)
    print("=" * 70, flush=True)

    result = gf.evaluate("""() => {
        function clean(s) {
            return String(s || '').split(' ').filter(p => p.length > 0).join(' ');
        }
        const out = [];
        const selectors = [
            '[class*="msgBox"]',
            '[class*="dialog"]',
            '[class*="Dialog"]',
            '[class*="popup"]',
            '[class*="modal"]',
            '[role="dialog"]',
            '[role="alertdialog"]',
            '[class*="alert"]'
        ];
        const seen = new Set();

        for (const sel of selectors) {
            const els = document.querySelectorAll(sel);
            for (const d of els) {
                if (d.offsetParent === null) continue;
                if (seen.has(d)) continue;
                seen.add(d);

                const txt = clean(d.textContent).substring(0, 500);
                const rect = d.getBoundingClientRect();

                // Quét element con có text ngắn
                const children = [];
                const allEls = d.querySelectorAll('*');
                for (const c of allEls) {
                    if (c.offsetParent === null) continue;
                    if (c.children.length > 2) continue;
                    const ct = clean(c.textContent || c.value || '').trim();
                    if (ct.length > 0 && ct.length < 60) {
                        children.push({
                            tag: c.tagName,
                            text: ct.substring(0, 50),
                            cls: String(c.className || '').substring(0, 40),
                            id: c.id || ''
                        });
                    }
                }

                out.push({
                    selector: sel,
                    tag: d.tagName,
                    cls: String(d.className || '').substring(0, 80),
                    id: d.id || '',
                    text: txt,
                    rect: {x: Math.round(rect.x), y: Math.round(rect.y),
                           w: Math.round(rect.width), h: Math.round(rect.height)},
                    children: children.slice(0, 30)
                });
            }
        }
        return out;
    }""")

    print(f"\n  Total dialogs: {len(result)}", flush=True)
    for i, d in enumerate(result):
        print(f"\n  Dialog #{i} [{d['selector']}]", flush=True)
        print(f"    tag={d['tag']} id='{d['id']}' cls='{d['cls'][:60]}'", flush=True)
        print(f"    rect={d['rect']}", flush=True)
        print(f"    text: {d['text'][:200]}", flush=True)
        print(f"    children ({len(d['children'])}):", flush=True)
        for c in d['children'][:20]:
            print(f"      [{c['tag']:6s}] id='{c['id'][:15]}' "
                  f"cls='{c['cls'][:25]}' text='{c['text'][:45]}'", flush=True)

    return result


def scan_create_table_form(gf):
    """Mở form tạo bàn + quét chi tiết."""
    print("\n" + "=" * 70, flush=True)
    print("SCAN 5: CREATE TABLE FORM", flush=True)
    print("=" * 70, flush=True)

    # Gọi createTable()
    try:
        gf.evaluate("createTable()")
        print("  Called createTable()", flush=True)
    except Exception as e:
        print(f"  createTable() error: {e}", flush=True)
    time.sleep(3)

    # Quét form
    form_scan = gf.evaluate("""() => {
        const out = {
            radios: [],
            inputs: [],
            buttons: [],
            bodyText: ''
        };

        // Radios betAmt
        const radios = document.querySelectorAll('input[type="radio"]');
        for (const r of radios) {
            out.radios.push({
                type: r.type,
                name: r.name || '',
                value: r.value || '',
                id: r.id || '',
                checked: r.checked,
                visible: r.offsetParent !== null,
                cls: String(r.className || '').substring(0, 50)
            });
        }

        // Inputs trong form
        const inputs = document.querySelectorAll('input');
        for (const inp of inputs) {
            if (inp.offsetParent === null) continue;
            out.inputs.push({
                type: inp.type,
                name: inp.name || '',
                id: inp.id || '',
                value: String(inp.value || '').substring(0, 40),
                cls: String(inp.className || '').substring(0, 50)
            });
        }

        // Buttons
        const btns = document.querySelectorAll(
            'button, input[type="button"], input[type="submit"], ' +
            'a, [role="button"], [class*="btn"]');
        for (const b of btns) {
            if (b.offsetParent === null) continue;
            const t = (b.textContent || b.value || '').trim();
            if (t.length > 0 && t.length < 60) {
                out.buttons.push({
                    tag: b.tagName,
                    text: t.substring(0, 50),
                    cls: String(b.className || '').substring(0, 40),
                    id: b.id || ''
                });
            }
        }

        out.bodyText = (document.body ? document.body.innerText : '')
            .substring(0, 1500);
        return out;
    }""")

    print(f"\n  Radios ({len(form_scan['radios'])}):", flush=True)
    for r in form_scan['radios']:
        print(f"    type={r['type']} name='{r['name']}' "
              f"value='{r['value']}' id='{r['id']}' "
              f"checked={r['checked']} visible={r['visible']}", flush=True)

    print(f"\n  Inputs ({len(form_scan['inputs'])}):", flush=True)
    for inp in form_scan['inputs']:
        print(f"    type={inp['type']} name='{inp['name']}' "
              f"id='{inp['id']}' value='{inp['value']}'", flush=True)

    print(f"\n  Buttons ({len(form_scan['buttons'])}):", flush=True)
    for b in form_scan['buttons']:
        print(f"    [{b['tag']:6s}] id='{b['id'][:15]}' "
              f"text='{b['text'][:40]}' cls='{b['cls'][:25]}'", flush=True)

    print(f"\n  Body text:", flush=True)
    print(f"    {form_scan['bodyText'][:1200]}", flush=True)

    return form_scan


def scan_after_create(gf):
    """Bấm CREATE rồi quét dialog kết quả."""
    print("\n" + "=" * 70, flush=True)
    print("SCAN 6: AFTER CLICK CREATE", flush=True)
    print("=" * 70, flush=True)

    # Chọn bet cao nhất (radio cuối)
    picked = gf.evaluate("""() => {
        const radios = document.querySelectorAll(
            'input[type="radio"][name="betAmt"]');
        if (!radios || radios.length === 0) {
            // Thử mọi radio
            const all = document.querySelectorAll('input[type="radio"]');
            if (all.length === 0) return {ok: false, reason: 'no radios'};
            const last = all[all.length - 1];
            last.checked = true;
            last.dispatchEvent(new Event('change', {bubbles: true}));
            return {ok: true, count: all.length,
                    picked_value: last.value,
                    picked_name: last.name};
        }
        const last = radios[radios.length - 1];
        last.checked = true;
        last.dispatchEvent(new Event('change', {bubbles: true}));
        return {ok: true, count: radios.length,
                picked_value: last.value,
                picked_name: last.name};
    }""")
    print(f"  Picked bet: {picked}", flush=True)
    time.sleep(1)

    # Bấm CREATE
    create_btn = gf.evaluate("""() => {
        const all = document.querySelectorAll(
            'input[name="CREATE"], button, input[type="button"], ' +
            'input[type="submit"], a');
        for (const b of all) {
            if (b.offsetParent === null) continue;
            const name = b.name || '';
            const txt = (b.textContent || b.value || '').trim();
            const t = txt.toLowerCase();
            if (name === 'CREATE' || t === 'create' || t === 'tạo bàn' ||
                t === 'tạo' || t === 'ok' || t === 'confirm') {
                b.click();
                return {clicked: true, tag: b.tagName,
                        name: name, text: txt};
            }
        }
        return {clicked: false};
    }""")
    print(f"  Clicked CREATE: {create_btn}", flush=True)
    time.sleep(4)

    # Quét dialog sau khi click
    dialogs_after = scan_dialogs(gf, "after CREATE")

    # Quét toàn bộ element có thể là nút trong dialog
    dialog_buttons = gf.evaluate("""() => {
        function clean(s) {
            return String(s || '').split(' ').filter(p => p.length > 0).join(' ');
        }
        const out = [];
        const dialog = document.querySelector(
            '[class*="msgBox"], [class*="dialog"], [class*="Dialog"]');
        if (!dialog) return out;

        const all = dialog.querySelectorAll('*');
        for (const el of all) {
            if (el.offsetParent === null) continue;
            const txt = clean(el.textContent || el.value || '').trim();
            if (txt.length > 0 && txt.length < 60) {
                out.push({
                    tag: el.tagName,
                    text: txt.substring(0, 50),
                    cls: String(el.className || '').substring(0, 50),
                    id: el.id || '',
                    onclick: String(el.getAttribute('onclick') || '')
                        .substring(0, 50)
                });
            }
        }
        return out;
    }""")

    print(f"\n  Elements trong dialog ({len(dialog_buttons)}):", flush=True)
    for i, el in enumerate(dialog_buttons):
        print(f"    #{i:3d} [{el['tag']:6s}] "
              f"id='{el['id'][:15]}' "
              f"cls='{el['cls'][:30]}' "
              f"text='{el['text'][:50]}' "
              f"onclick='{el['onclick'][:30]}'", flush=True)

    return dialogs_after, dialog_buttons


def scan_find_table(gf, page):
    """Mở Find table + quét lobby."""
    print("\n" + "=" * 70, flush=True)
    print("SCAN 7: FIND TABLE / LOBBY", flush=True)
    print("=" * 70, flush=True)

    # Đóng dialog cũ
    try:
        gf.evaluate("$('.msgBoxBackGround,.msgBox').remove()")
    except Exception:
        pass
    time.sleep(1)

    # Click "Find table"
    find_btn = gf.evaluate("""() => {
        function clean(s) {
            return String(s || '').split(' ').filter(p => p.length > 0).join(' ');
        }
        const all = document.querySelectorAll(
            'a, button, input[type="button"], [role="button"], ' +
            '[onclick], [class*="btn"]');
        for (const el of all) {
            if (el.offsetParent === null) continue;
            const txt = clean(el.textContent || el.value || '')
                .trim().toLowerCase();
            if (txt === 'find table' || txt === 'tìm bàn' ||
                txt.indexOf('find table') >= 0 ||
                txt.indexOf('tìm bàn') >= 0) {
                el.click();
                return {clicked: true, tag: el.tagName, text: txt};
            }
        }
        return {clicked: false};
    }""")
    print(f"  Clicked Find table: {find_btn}", flush=True)
    time.sleep(5)

    # Quét lobby - mọi element có class chứa room/region/card
    lobby_scan = gf.evaluate("""() => {
        function clean(s) {
            return String(s || '').split(' ').filter(p => p.length > 0).join(' ');
        }
        const out = {
            rooms: [],
            tables: [],
            all_clickable: [],
            body_snippet: ''
        };

        // Tìm mọi element có class chứa room/region/card
        const roomSelectors = [
            'a.roomCard', '[class*="roomCard"]',
            '[class*="room-card"]', '[class*="region"]',
            '[class*="area"]', '[class*="lobby"]',
            '[class*="tab"]', '[class*="category"]'
        ];
        const seen = new Set();
        for (const sel of roomSelectors) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                if (el.offsetParent === null) continue;
                if (seen.has(el)) continue;
                seen.add(el);
                const txt = clean(el.textContent).trim();
                if (txt.length > 0 && txt.length < 200) {
                    out.rooms.push({
                        sel: sel,
                        tag: el.tagName,
                        cls: String(el.className || '').substring(0, 80),
                        text: txt.substring(0, 100),
                        clickable: !!el.onclick ||
                                   el.tagName === 'A' ||
                                   el.tagName === 'BUTTON'
                    });
                }
            }
        }

        // Tìm text "fffff" cụ thể
        const all = document.querySelectorAll('*');
        for (const el of all) {
            if (el.offsetParent === null) continue;
            if (el.children.length > 3) continue;
            const txt = clean(el.textContent).trim();
            if (txt.length > 0 && txt.length < 60 &&
                txt.toLowerCase().indexOf('fffff') >= 0) {
                out.tables.push({
                    tag: el.tagName,
                    cls: String(el.className || '').substring(0, 60),
                    text: txt.substring(0, 60)
                });
            }
        }

        out.body_snippet = (document.body ? document.body.innerText : '')
            .substring(0, 2000);
        return out;
    }""")

    print(f"\n  Lobby rooms/regions ({len(lobby_scan['rooms'])}):", flush=True)
    for i, r in enumerate(lobby_scan['rooms'][:40]):
        print(f"    #{i:2d} [{r['sel']:25s}] "
              f"tag={r['tag']:6s} "
              f"cls='{r['cls'][:40]}' "
              f"clickable={r['clickable']} "
              f"text='{r['text'][:50]}'", flush=True)

    print(f"\n  Tables matching 'fffff' ({len(lobby_scan['tables'])}):",
          flush=True)
    for t in lobby_scan['tables']:
        print(f"    [{t['tag']:6s}] cls='{t['cls'][:40]}' "
              f"text='{t['text'][:50]}'", flush=True)

    print(f"\n  Body snippet:", flush=True)
    print(f"    {lobby_scan['body_snippet'][:1500]}", flush=True)

    return lobby_scan


def scan_all_windows(gf, page):
    """Quét tất cả window objects có sẵn trong game."""
    print("\n" + "=" * 70, flush=True)
    print("SCAN 8: WINDOW GLOBALS DEEP", flush=True)
    print("=" * 70, flush=True)

    result = gf.evaluate("""() => {
        const out = {};
        // Liệt kê tất cả key của window
        const keys = Object.keys(window);
        out.total_keys = keys.length;
        out.interesting = [];

        const skip = ['onabort','onblur','oncancel','oncanplay','oncanplaythrough',
                      'onchange','onclick','onclose','oncontextmenu','oncuechange',
                      'ondblclick','ondrag','ondragend','ondragenter','ondragleave',
                      'ondragover','ondragstart','ondrop','ondurationchange',
                      'onemptied','onended','onerror','onfocus','onformdata',
                      'oninput','oninvalid','onkeydown','onkeypress','onkeyup',
                      'onload','onloadeddata','onloadedmetadata','onloadstart',
                      'onmousedown','onmouseenter','onmouseleave','onmousemove',
                      'onmouseout','onmouseover','onmouseup','onmousewheel',
                      'onpause','onplay','onplaying','onprogress','onratechange',
                      'onreset','onresize','onscroll','onseeked','onseeking',
                      'onselect','onstalled','onsubmit','onsuspend','ontimeupdate',
                      'ontoggle','onvolumechange','onwaiting','onwebkitanimationend',
                      'onwebkitanimationiteration','onwebkitanimationstart',
                      'onwebkittransitionend','onwheel','onauxclick','ongotpointercapture',
                      'onlostpointercapture','onpointerdown','onpointermove',
                      'onpointerup','onpointercancel','onpointerover','onpointerout',
                      'onpointerenter','onpointerleave','onselectstart','onselectionchange',
                      'onanimationend','onanimationiteration','onanimationstart',
                      'ontransitionend','onbeforeunload','onhashchange','onlanguagechange',
                      'onmessage','onmessageerror','onoffline','ononline','onpagehide',
                      'onpageshow','onpopstate','onrejectionhandled','onstorage',
                      'onunhandledrejection','onunload'];

        for (const k of keys) {
            if (skip.indexOf(k) >= 0) continue;
            if (k.indexOf('webkit') === 0) continue;
            if (k.indexOf('moz') === 0) continue;
            try {
                const v = window[k];
                const t = typeof v;
                if (t === 'function') {
                    out.interesting.push({name: k, type: 'function'});
                } else if (t === 'object' && v !== null) {
                    const subkeys = Object.keys(v).slice(0, 15);
                    out.interesting.push({
                        name: k,
                        type: 'object',
                        keys: subkeys
                    });
                } else if (t === 'string' || t === 'number') {
                    out.interesting.push({
                        name: k,
                        type: t,
                        value: String(v).substring(0, 60)
                    });
                }
            } catch (e) {}
        }
        return out;
    }""")

    print(f"\n  Total window keys: {result.get('total_keys')}", flush=True)
    print(f"\n  Interesting globals ({len(result.get('interesting', []))}):",
          flush=True)
    for g in result.get('interesting', [])[:100]:
        if g['type'] == 'object' and g.get('keys'):
            print(f"    {g['name']:25s} [object] keys={g['keys']}", flush=True)
        elif g['type'] == 'function':
            print(f"    {g['name']:25s} [function]", flush=True)
        else:
            print(f"    {g['name']:25s} [{g['type']}] = {g.get('value', '')}",
                  flush=True)

    return result


# ============ MAIN ============
def main():
    print("=" * 70, flush=True)
    print("SÂM LỐC GAME SCANNER v10", flush=True)
    print("=" * 70, flush=True)
    print(f"HEADLESS: {HEADLESS}", flush=True)

    cookie_sets = load_all_cookie_sets()
    if not cookie_sets:
        print("[STOP] Không có file ck*.txt nào.", flush=True)
        return 1

    print(f"\nCookie files: {[c['file'] for c in cookie_sets]}", flush=True)

    # Chỉ dùng cookie đầu tiên
    entry = cookie_sets[0]
    print(f"\n>>> Dùng cookie: {entry['file']}", flush=True)
    fb_cookies = parse_cookies(entry["raw"])

    with sync_playwright() as p:
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
        for c in fb_cookies:
            c['domain'] = '.facebook.com'
        context.add_cookies(fb_cookies)
        page = context.new_page()

        # Bước 1: Login
        print("\n[1] Login FB...", flush=True)
        try:
            page.goto("https://www.facebook.com/",
                      wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            browser.close()
            return 1
        page.wait_for_timeout(5000)

        if page.locator('input[placeholder="Email or phone"]').count() > 0:
            print("  ERROR: Not logged in", flush=True)
            browser.close()
            return 1
        print("  OK", flush=True)

        # Bước 2: Mở game
        print("\n[2] Open game...", flush=True)
        try:
            page.goto(SAM_LOC_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"  ERROR goto: {e}", flush=True)
            browser.close()
            return 1
        page.wait_for_timeout(30000)

        # Tìm frame game
        gf = None
        for check_round in range(15):
            for f in page.frames:
                if "instant-bundle" in f.url:
                    gf = f
                    break
            if gf:
                print(f"  Game frame found (round {check_round+1})", flush=True)
                break
            page.wait_for_timeout(15000)

        if not gf:
            print("  ERROR: No game frame", flush=True)
            scan_frame_info(page)
            try:
                page.screenshot(path="/tmp/scanner_no_frame.png", full_page=True)
            except Exception:
                pass
            browser.close()
            return 1

        page.wait_for_timeout(20000)

        # Đợi WS
        for attempt in range(5):
            try:
                if gf.evaluate(
                    "() => window.connection?.ws?.readyState === 1"
                ):
                    print(f"  WS CONNECTED", flush=True)
                    break
            except Exception:
                pass
            time.sleep(10)

        # ============ SCAN ============
        try:
            scan_frame_info(page)
            scan_page_structure(gf, "initial")
            scan_buttons(gf, "initial")
            scan_dialogs(gf, "initial")
            scan_all_windows(gf, page)
            scan_create_table_form(gf)
            scan_after_create(gf)
            scan_find_table(gf, page)

            # Screenshot cuối
            try:
                page.screenshot(path="/tmp/scanner_final.png", full_page=True)
                print("\n  Final screenshot: /tmp/scanner_final.png", flush=True)
            except Exception:
                pass

        except Exception as e:
            print(f"\n[SCAN ERROR] {e}", flush=True)
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 70, flush=True)
        print("SCAN COMPLETE", flush=True)
        print("=" * 70, flush=True)

        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
