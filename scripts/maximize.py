"""Score maximizer: drop a test script into a project, run it, read the score, repeat.

This is the whole competition loop in one command — useful when adapting to a new
problem: write one script, point this at it, and watch the score until it stops moving.

    python maximize.py <pid> <script.py> [--slot <existing .py name>] [--seq 1]
                        [--rounds 3] [--target 100] [--gap 2]

Score source priority: the SUT's TCP score service (instant, port 10308) then the
exam-client UI (needs the CDP browser, slower).

Why rounds: flags are sticky, but frame delivery is not reliable — a second pass in a
fresh task catches whatever the first pass lost to buffer coalescing or modal dialogs.
Two rounds is usually enough; the loop stops early when the score stops improving.
"""
import argparse
import glob
import os
import shutil
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from et5 import ET5  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def scripts_dir(pid):
    base = os.path.join(os.environ.get("APPDATA", ""), ".etest5-workspace", pid)
    for name in ("scripts", "script"):
        p = os.path.join(base, name)
        if os.path.isdir(p):
            return p
    return os.path.join(base, "scripts")


def tcp_score(port=10308, host="127.0.0.1"):
    import socket
    s = socket.socket()
    s.settimeout(2.5)
    try:
        s.connect((host, port))
        s.sendall(b"\xff\xff\x01\xf0" + struct.pack("<f", 1.4))
        buf = b""
        while len(buf) < 17:
            chunk = s.recv(64)
            if not chunk:
                break
            buf += chunk
        if len(buf) < 11:
            return None
        return struct.unpack("<d", buf[3:11])[0]
    except Exception:
        return None
    finally:
        s.close()


def ui_score():
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, "score.py")],
                           capture_output=True, text=True, timeout=180)
        for line in (p.stdout or "").splitlines():
            if line.startswith("SCORE:"):
                v = line.split(":", 1)[1].strip()
                return float(v) if v != "None" else None
    except Exception:
        pass
    return None


def score():
    v = tcp_score()
    return v if v is not None else ui_score()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("script")
    ap.add_argument("--slot", help="existing script filename to overwrite")
    ap.add_argument("--seq", default="1", help="sequence index or name substring")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--target", type=float, default=100.0)
    ap.add_argument("--gap", type=float, default=2.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    d = scripts_dir(a.pid)
    if not os.path.isdir(d):
        print("no script dir:", d)
        return 1
    slot = a.slot
    if not slot:
        py = sorted(glob.glob(os.path.join(d, "*.py")))
        if not py:
            print("no .py in", d)
            return 1
        slot = os.path.basename(py[0])
    dst = os.path.join(d, slot)
    print("slot:", dst)
    print("script:", a.script)
    if a.dry_run:
        print("dry-run, nothing executed")
        return 0

    c = ET5()
    if not c.login():
        print("login failed")
        return 1
    c.open(a.pid)
    seqs = c.sequences(a.pid)
    seq = None
    if a.seq.isdigit() and 0 < int(a.seq) <= len(seqs):
        seq = seqs[int(a.seq) - 1]
    else:
        seq = next((s for s in seqs if a.seq in (s.get("name") or "")), None)
    if not seq:
        print("sequence not found; available:")
        for i, s in enumerate(seqs, 1):
            print(" %2d %s" % (i, s.get("name")))
        return 1
    print("sequence:", seq.get("name"))

    best = score()
    print("start score:", best, flush=True)
    stall = 0
    for rnd in range(1, a.rounds + 1):
        shutil.copyfile(a.script, dst)
        res = c.run(a.pid, seq["id"], timeout=600)
        time.sleep(a.gap)
        cur = score()
        print("round %d: %s  score=%s" % (rnd, res, cur), flush=True)
        if cur is None:
            break
        if best is None or cur > best + 0.001:
            best, stall = cur, 0
        else:
            stall += 1
        if best is not None and best >= a.target:
            print("target reached")
            break
        if stall >= 2:
            print("no improvement twice, stopping")
            break
    print("FINAL:", best)
    return 0


if __name__ == "__main__":
    sys.exit(main())
