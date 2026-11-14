"""SUT (device under test) window/COM helpers — Win32, stdlib only.

    python sut.py ports                       # list COM ports
    python sut.py dialogs                     # list modal dialogs
    python sut.py dismiss                     # close modal dialogs (one pass)
    python sut.py watch [--interval 1]        # watchdog loop (run as a daemon)
    python sut.py click "<title>"             # click default button of a dialog
    python sut.py capture "<title>" out.bmp   # PrintWindow capture (z-order proof)

Modal dialogs matter: a WinForms message box blocks the SUT's UI thread, so every
later test fails or times out. `watch` clears them automatically and logs the body
text, which doubles as defect evidence.
"""
import argparse
import ctypes
import os
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.windll.gdi32


def _set_dpi_aware():
    """Per-monitor v2 first: at 175% scaling a system-aware process still gets physical
    pixels for GetWindowRect, but v2 is correct on mixed-DPI and multi-monitor setups."""
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
        return "system"
    except Exception:
        return "none"


DPI_MODE = _set_dpi_aware()

TITLES = ("\u4fe1\u606f\u63d0\u793a", "\u9519\u8bef", "\u63d0\u793a", "\u8b66\u544a",
          "\u5f02\u5e38", "\u5931\u8d25")
LOG = os.environ.get("SUT_LOG", os.path.join(os.path.expanduser("~"), "sut_dialogs.log"))

BM_CLICK = 0x00F5
SMTO_ABORTIFHUNG = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _click(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    inp = INPUT()
    inp.type = 0
    inp.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    time.sleep(0.06)
    inp.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    time.sleep(0.25)


def _exe(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    buf = ctypes.create_unicode_buffer(512)
    size = ctypes.c_ulong(512)
    try:
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def _children(h):
    out = []

    def cb(c, _):
        cn = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(c, cn, 128)
        n = user32.GetWindowTextLengthW(c)
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(c, b, n + 1)
        out.append((c, cn.value, b.value))
        return True

    user32.EnumChildWindows(h, Proc(cb), 0)
    return out


def windows(title_filter=None):
    out = []

    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if not n:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, b, n + 1)
        title = b.value
        if title_filter and title_filter not in title:
            return True
        if not title_filter and not any(t in title for t in TITLES):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        out.append({"hwnd": h, "title": title, "pid": pid.value, "exe": _exe(pid.value),
                    "rect": (r.left, r.top, r.right, r.bottom)})
        return True

    user32.EnumWindows(Proc(cb), 0)
    return out


def body_text(h):
    parts = [t for _, cn, t in _children(h) if t and "BUTTON" not in cn]
    return " / ".join(parts)[:300]


def press_ok(h):
    """Click the affirmative button of a dialog.

    Text matching is unreliable on these WinForms dialogs (mojibake in GetWindowText),
    so fall back to geometry: 确定 sits left of 关闭 in the bottom row.
    """
    btns = []
    for c, cn, txt in _children(h):
        if "BUTTON" in cn:
            r = wintypes.RECT()
            user32.GetWindowRect(c, ctypes.byref(r))
            btns.append((c, txt, r.left, r.top, r.right, r.bottom))

    for c, txt, l, t, rr, bb in btns:
        up = txt.upper()
        if "\u786e\u5b9a" in txt or "OK" in up or "&O" in up:
            res = ctypes.c_size_t()
            user32.SendMessageTimeoutW(c, BM_CLICK, 0, 0, SMTO_ABORTIFHUNG, 1500, ctypes.byref(res))
            return "button"

    if btns:
        # 再退一步：排除"关闭/取消"这类否定按钮，取剩下最靠左的（确定通常在左）
        neg = ("\u5173\u95ed", "\u53d6\u6d88", "CANCEL", "\u5426")
        cand = [b for b in btns if not any(n in b[1].upper() for n in neg)]
        cand.sort(key=lambda b: (b[3], b[2]))
        pick = cand[0] if cand else sorted(btns, key=lambda b: (b[3], b[2]))[0]
        c = pick[0]
        res = ctypes.c_size_t()
        user32.SendMessageTimeoutW(c, BM_CLICK, 0, 0, SMTO_ABORTIFHUNG, 1500, ctypes.byref(res))
        return "button-by-position"

    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    try:
        user32.SetForegroundWindow(h)
    except Exception:
        pass
    time.sleep(0.3)
    # Last resort: click a proportional spot in the bottom button row (never fixed pixels —
    # at 175% scaling a 45 px offset can land on 关闭 instead of 确定).
    w = max(1, r.right - r.left)
    hh = max(1, r.bottom - r.top)
    _click(r.left + w * 0.70, r.bottom - hh * 0.075)
    return "coord"


def cmd_screen(_):
    """Print what the UI automation actually sees — run this first when the display changes."""
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    try:
        dpi = user32.GetDpiForSystem()
    except Exception:
        dpi = 96
    pct = int(round(dpi * 100.0 / 96))
    print("dpi mode : %s" % DPI_MODE)
    print("screen   : %dx%d" % (w, h))
    print("dpi      : %d (%d%%)" % (dpi, pct))
    print("mouse px : physical (SendInput/SetCursorPos use these units)")
    if DPI_MODE == "none":
        print("WARNING  : DPI awareness failed; window rects may be virtualised")
    if pct != 100:
        print("note     : scaled display — all clicks go through window handles; the only\n"
              "           pixel path is the dialog fallback, which is proportional now")
    return 0


def cmd_ports(_):
    try:
        import serial.tools.list_ports as lp
        for p in lp.comports():
            print("%-8s %s" % (p.device, p.description))
        return 0
    except Exception:
        pass
    import winreg
    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
    i = 0
    while True:
        try:
            name, val, _ = winreg.EnumValue(key, i)
            print("%-8s %s" % (val, name))
            i += 1
        except OSError:
            break
    return 0


def cmd_dialogs(_):
    ds = windows()
    for d in ds:
        print("%s | pid=%s exe=%s | %s" % (d["title"], d["pid"], d["exe"], body_text(d["hwnd"])))
    if not ds:
        print("(none)")
    return 0


def cmd_dismiss(_):
    n = 0
    for _ in range(10):
        ds = windows()
        if not ds:
            break
        how = press_ok(ds[0]["hwnd"])
        print("closed:", ds[0]["title"], "via", how, "|", body_text(ds[0]["hwnd"])[:120])
        n += 1
        time.sleep(0.4)
    print("handled:", n)
    return 0


def cmd_watch(a):
    print("watching modal dialogs, log ->", LOG, flush=True)
    while True:
        try:
            for d in windows():
                how = press_ok(d["hwnd"])
                line = "%s close(%s) pid=%s exe=%s body=%s" % (
                    time.strftime("%Y-%m-%d %H:%M:%S"), how, d["pid"], d["exe"], body_text(d["hwnd"]))
                print(line, flush=True)
                with open(LOG, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            print("watch error:", e, flush=True)
        time.sleep(a.interval)


def cmd_click(a):
    ds = windows(a.title)
    if not ds:
        print("no window matching", a.title)
        return 1
    how = press_ok(ds[0]["hwnd"])
    print("clicked", ds[0]["title"], "via", how)
    return 0


def _combos(title):
    """Port-config dialogs are ordinary WinForms ComboBoxes; list them in reading order."""
    root = 0
    for d in windows(title):
        root = d["hwnd"]
        break
    if not root:
        return []
    out = []

    def cb(h, _):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        if "COMBOBOX" in cls.value:
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            out.append((h, r.left, r.top))
        return True

    user32.EnumChildWindows(root, Proc(cb), 0)
    out.sort(key=lambda x: (x[2], x[1]))
    return out


def _items(h):
    CB_GETCOUNT, CB_GETCURSEL, CB_GETLBTEXT, CB_GETLBTEXTLEN = 0x0146, 0x0147, 0x0148, 0x0149
    n = user32.SendMessageW(h, CB_GETCOUNT, 0, 0)
    sel = user32.SendMessageW(h, CB_GETCURSEL, 0, 0)
    items = []
    for i in range(min(n, 40)):
        ln = user32.SendMessageW(h, CB_GETLBTEXTLEN, i, 0)
        buf = ctypes.create_unicode_buffer(ln + 1)
        user32.SendMessageW(h, CB_GETLBTEXT, i, ctypes.byref(buf))
        items.append(buf.value)
    return sel, items


def cmd_combos(a):
    cs = _combos(a.title)
    if not cs:
        print("no combo boxes under", a.title)
        return 1
    for i, (h, x, y) in enumerate(cs):
        sel, items = _items(h)
        print("%2d @(%d,%d) sel=%d %s" % (i, x, y, sel, items))
    return 0


def cmd_combo_set(a):
    cs = _combos(a.title)
    if a.index >= len(cs):
        print("index out of range, have", len(cs))
        return 1
    h = cs[a.index][0]
    sel, items = _items(h)
    if a.value not in items:
        print("no such item; have", items)
        return 1
    idx = items.index(a.value)
    user32.SendMessageW(h, 0x014E, idx, 0)         # CB_SETCURSEL
    # WinForms needs the notification to push the value into the bound property
    parent = user32.GetParent(h)
    user32.SendMessageW(parent, 0x0111, (1 << 16) | user32.GetDlgCtrlID(h), h)   # WM_COMMAND CBN_SELCHANGE
    print("set combo %d -> %s" % (a.index, a.value))
    return 0


def cmd_capture(a):
    h = 0
    for d in windows(a.title):
        h = d["hwnd"]
        break
    if not h:
        print("no window matching", a.title)
        return 1
    if user32.IsIconic(h):
        user32.ShowWindow(h, 9)
        time.sleep(0.6)
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    w, ht = r.right - r.left, r.bottom - r.top
    dc = user32.GetWindowDC(h)
    mem = gdi32.CreateCompatibleDC(dc)
    bmp = gdi32.CreateCompatibleBitmap(dc, w, ht)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(h, mem, 2)

    class BI(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    bi = BI()
    bi.biSize = ctypes.sizeof(BI)
    bi.biWidth = w
    bi.biHeight = -ht
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * ht * 4)
    gdi32.GetDIBits(mem, bmp, 0, ht, buf, ctypes.byref(bi), 0)
    hdr = b"BM" + (54 + len(buf)).to_bytes(4, "little") + b"\0\0\0\0" + (54).to_bytes(4, "little")
    open(a.out, "wb").write(hdr + ctypes.string_at(ctypes.byref(bi), ctypes.sizeof(bi)) + buf.raw)
    print("saved", a.out, w, "x", ht)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports")
    sub.add_parser("screen")
    sub.add_parser("dialogs")
    sub.add_parser("dismiss")
    p = sub.add_parser("watch"); p.add_argument("--interval", type=float, default=1.0)
    p = sub.add_parser("click"); p.add_argument("title")
    p = sub.add_parser("combos"); p.add_argument("title")
    p = sub.add_parser("combo-set"); p.add_argument("title"); p.add_argument("index", type=int)
    p.add_argument("value")
    p = sub.add_parser("capture"); p.add_argument("title"); p.add_argument("out")
    a = ap.parse_args()
    {"ports": cmd_ports, "dialogs": cmd_dialogs, "dismiss": cmd_dismiss,
     "watch": cmd_watch, "click": cmd_click, "capture": cmd_capture,
     "combos": cmd_combos, "combo-set": cmd_combo_set, "screen": cmd_screen}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
