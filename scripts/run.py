"""Sequence runner / channel binder for ETest5 projects.

    python run.py projects
    python run.py list   <pid>
    python run.py one    <pid> <index|name-substr> [--timeout 300]
    python run.py all    <pid> [--order 9,8,7] [--last 接口3,功能4] [--timeout 300]
    python run.py patch  <pid> [--restore]      # inject ask() auto-answer
    python run.py cards                          # list cardInstanceId in use
    python run.py bind   <pid> Name=COM2 Name2=COM4 [--card UUID] [--relines]
    python run.py channels <pid>

`all` writes etest5-results-<ts>.json to the current directory.
"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from et5 import ET5  # noqa: E402

PATCH = "ask = lambda *a, **k: True   # AUTO_ASK_PATCH"


def ws_scripts(pid):
    return os.path.join(os.environ.get("APPDATA", ""), ".etest5-workspace", pid, "scripts")


def do_patch(pid, restore=False):
    d = ws_scripts(pid)
    files = sorted(glob.glob(os.path.join(d, "*.py")))
    if not files:
        print("no scripts under", d)
        return
    for f in files:
        src = open(f, encoding="utf-8").read()
        bak = f + ".bak"
        if restore:
            if os.path.exists(bak):
                open(f, "w", encoding="utf-8").write(open(bak, encoding="utf-8").read())
                os.remove(bak)
                print("restored", os.path.basename(f))
            continue
        if PATCH in src:
            continue
        if not os.path.exists(bak):
            open(bak, "w", encoding="utf-8").write(src)
        out, done = [], False
        for line in src.splitlines():
            out.append(line)
            if not done and line.startswith("from etest import"):
                out.append(PATCH)
                done = True
        if not done:
            out.insert(0, PATCH)
        open(f, "w", encoding="utf-8").write("\n".join(out) + "\n")
        print("patched", os.path.basename(f))


def pick(seqs, key):
    if key.isdigit():
        i = int(key) - 1
        return seqs[i] if 0 <= i < len(seqs) else None
    for s in seqs:
        if key in (s.get("name") or ""):
            return s
    return None


def cmd_all(c, pid, args):
    seqs = c.sequences(pid)
    if not seqs:
        print("no sequences")
        return 1
    order = list(range(1, len(seqs) + 1))
    if args.order:
        order = [int(x) for x in args.order.split(",") if x.strip()]
    last = [x.strip() for x in (args.last or "").split(",") if x.strip()]
    if last:
        head = [i for i in order if not any(k in (seqs[i - 1].get("name") or "") for k in last)]
        tail = [i for i in order if i not in head]
        order = head + tail

    results = []
    for i in order:
        s = seqs[i - 1]
        print("\n>>> [%d] %s" % (i, s.get("name")), flush=True)
        t0 = time.time()
        res = c.run(pid, s["id"], timeout=args.timeout)
        print("   -> %s  (%.0fs)" % (res, time.time() - t0), flush=True)
        results.append({"index": i, "name": s.get("name"), "result": res,
                        "seconds": round(time.time() - t0, 1)})

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(os.getcwd(), "etest5-results-%s.json" % stamp)
    json.dump({"pid": pid, "results": results}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n" + "=" * 52)
    ok = sum(1 for r in results if r["result"] == "PASSED")
    for r in results:
        print("  %-34s %s" % (r["name"][:34], r["result"]))
    print("  %d/%d PASSED   -> %s" % (ok, len(results), out))
    return 0


def cmd_cards(c):
    seen = {}
    for p in c.projects():
        pid = p.get("id")
        try:
            ch = c.kv_get(pid, "module.channel") or []
        except Exception:
            continue
        for eng in ch:
            for chn in eng.get("channels", []):
                card = (chn.get("port") or {}).get("cardInstanceId")
                if card:
                    seen.setdefault(card, []).append(p.get("name"))
    for card, names in seen.items():
        print("%s  used by: %s" % (card, ", ".join(sorted(set(names))[:3])))
    if not seen:
        print("no cardInstanceId found")


def cmd_bind(c, pid, args):
    ch = c.kv_get(pid, "module.channel")
    if not ch:
        print("module.channel empty")
        return 1
    want = {}
    for kv in args.map:
        k, v = kv.split("=", 1)
        want[k] = v
    n = 0
    for eng in ch:
        for chn in eng.get("channels", []):
            name = chn.get("name")
            if name not in want:
                continue
            port = chn.setdefault("port", {})
            port["physicalPort"] = want[name]
            port["portType"] = port.get("portType") or "S232"
            if args.card:
                port["cardInstanceId"] = args.card
            if args.relines:
                port["line"] = n
                chn["bind"] = "SERIAL::S232::%d" % n
            n += 1
            print("%-10s -> %s line=%s card=%s" % (name, port["physicalPort"],
                                                   port.get("line"), (port.get("cardInstanceId") or "")[:8]))
    print("save:", (c.kv_set(pid, "module.channel", ch) or {}).get("msg"))
    return 0


def cmd_channels(c, pid):
    ch = c.kv_get(pid, "module.channel") or []
    for eng in ch:
        for chn in eng.get("channels", []):
            p = chn.get("port") or {}
            q = chn.get("params") or {}
            print("%-10s %-6s line=%-2s %-6s bind=%s" % (
                chn.get("name"), p.get("physicalPort"), p.get("line"),
                q.get("baudrate"), chn.get("bind")))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("projects")
    p = sub.add_parser("list"); p.add_argument("pid")
    p = sub.add_parser("one"); p.add_argument("pid"); p.add_argument("key"); p.add_argument("--timeout", type=int, default=300)
    p = sub.add_parser("all"); p.add_argument("pid")
    p.add_argument("--order"); p.add_argument("--last"); p.add_argument("--timeout", type=int, default=300)
    p = sub.add_parser("patch"); p.add_argument("pid"); p.add_argument("--restore", action="store_true")
    sub.add_parser("cards")
    p = sub.add_parser("bind"); p.add_argument("pid"); p.add_argument("map", nargs="+")
    p.add_argument("--card"); p.add_argument("--relines", action="store_true")
    p = sub.add_parser("channels"); p.add_argument("pid")

    a = ap.parse_args()
    c = ET5()
    if not c.login():
        print("login failed")
        return 1

    if a.cmd == "projects":
        for x in c.projects():
            print("%-40s %s" % (x.get("id"), x.get("name")))
        return 0
    if a.cmd == "cards":
        cmd_cards(c)
        return 0

    c.open(a.pid)
    if a.cmd == "list":
        for i, s in enumerate(c.sequences(a.pid), 1):
            print("%2d  %-40s %s" % (i, s.get("name"), s.get("id")))
    elif a.cmd == "one":
        s = pick(c.sequences(a.pid), a.key)
        if not s:
            print("sequence not found")
            return 1
        print(">>> %s" % s.get("name"))
        print("RESULT:", c.run(a.pid, s["id"], timeout=a.timeout))
    elif a.cmd == "all":
        return cmd_all(c, a.pid, a)
    elif a.cmd == "patch":
        do_patch(a.pid, a.restore)
    elif a.cmd == "bind":
        return cmd_bind(c, a.pid, a)
    elif a.cmd == "channels":
        cmd_channels(c, a.pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
