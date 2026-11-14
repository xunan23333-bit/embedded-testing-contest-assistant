"""Probe sweep: one candidate frame per task run, read the score after each, print deltas.

This is how you find out *which* probe is missing a flag without reading the SUT's memory.
Flags are sticky, so a positive delta means "that frame earned something new"; a zero delta
means it is already covered or the frame never landed (bad frames block the port — give them
a bigger gap, or move them to the end).

    python sweep.py <pid> <seq> --probes probes.txt [--gap 1.2] [--stop-on-zero N]

probes.txt:

    MAP S=Speed F2=setting F1=gas
    speed60|S FF 55 08 04 00 00 70 42 BE 00 FF 55
    stop|F2 FF 55 01 02 FF FF 01 02 FF 55

Writes sweep-results-<ts>.json next to the probes file.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from et5 import ET5  # noqa: E402
import maximize  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPLAY = os.path.join(HERE, "replay_snippet.py")


def parse_probes(path):
    mapping, probes = {}, []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.upper().startswith("MAP"):
                for kv in line.split()[1:]:
                    k, v = kv.split("=", 1)
                    mapping[k] = v
                continue
            label, rest = line.split("|", 1)
            alias, hexstr = rest.strip().split(None, 1)
            probes.append((label.strip(), alias.strip(), hexstr.strip()))
    return mapping, probes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("seq")
    ap.add_argument("--probes", required=True)
    ap.add_argument("--gap", type=float, default=1.2)
    ap.add_argument("--stop-on-zero", type=int, default=0,
                    help="stop after N consecutive probes with no gain")
    ap.add_argument("--frames", default=os.path.join(os.environ.get("TEMP", "."), "frames.txt"))
    a = ap.parse_args()

    mapping, probes = parse_probes(a.probes)
    if not probes:
        print("no probes")
        return 1

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
        print("sequence not found")
        return 1

    slot_dir = maximize.scripts_dir(a.pid)
    slot = sorted(glob.glob(os.path.join(slot_dir, "*.py")))[0]
    shutil.copyfile(REPLAY, slot)
    print("replay ->", slot)
    print("sequence:", seq.get("name"))

    prev = maximize.score()
    print("start score:", prev, flush=True)
    rows, zero = [], 0
    for label, alias, hexstr in probes:
        with open(a.frames, "w", encoding="utf-8") as f:
            f.write("MAP " + " ".join("%s=%s" % (k, v) for k, v in mapping.items()) + "\n")
            f.write("%s %s\n" % (alias, hexstr))
        res = c.run(a.pid, seq["id"], timeout=300)
        time.sleep(a.gap)
        cur = maximize.score()
        delta = (cur - prev) if isinstance(cur, float) and isinstance(prev, float) else None
        rows.append({"probe": label, "alias": alias, "hex": hexstr,
                     "result": res, "score": cur, "delta": delta})
        print("%-14s %s  %6s -> %s (%s)" % (label, res, prev, cur,
                                            ("+%.0f" % delta) if delta is not None else "?"), flush=True)
        if delta is not None:
            zero = zero + 1 if delta <= 0.001 else 0
            prev = cur
        if a.stop_on_zero and zero >= a.stop_on_zero:
            print("no gain for %d probes, stopping" % zero)
            break

    out = os.path.join(os.path.dirname(os.path.abspath(a.probes)),
                       "sweep-results-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    json.dump({"pid": a.pid, "seq": seq.get("name"), "rows": rows},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    gain = sum(r["delta"] for r in rows if r["delta"])
    print("\ntotal gain: %.0f   -> %s" % (gain, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
