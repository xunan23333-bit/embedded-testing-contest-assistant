# Generic frame replayer — put this in a project's scripts dir and run its sequence.
# Plan file (env FRAMES_FILE, default ./frames.txt next to the task):
#
#   MAP S=Speed F2=setting F1=gas
#   S  FF 55 08 04 00 00 70 42 BE 00 FF 55
#   F2 FF 55 01 02 00 00 03 00 FF 55
#
# First token is a port alias declared on the MAP line; `#` starts a comment.
# Gap between frames is 900 ms by default — raise it for frames that make the SUT pop
# a modal dialog (those block that port's thread until someone clicks OK).
import os

from etest import etimer, ebuff

PLAN = os.environ.get("FRAMES_FILE", os.path.join(os.getcwd(), "frames.txt"))
GAP_MS = int(os.environ.get("FRAMES_GAP_MS", "900"))


def entry(opt=None):
    mapping = {}
    steps = []
    with open(PLAN, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.upper().startswith("MAP"):
                for kv in line.split()[1:]:
                    k, v = kv.split("=", 1)
                    mapping[k] = v
                continue
            parts = line.split(None, 1)
            steps.append((parts[0], parts[1].strip()))

    # touch every declared channel once so the engine binds them all for this task
    for name in sorted(set(mapping.values())):
        try:
            channels[name]
        except Exception as e:
            print("channel %s unavailable: %s" % (name, e))

    for alias, hexstr in steps:
        ch = channels[mapping.get(alias, alias)]
        ch.write_buff(ebuff.from_hex(hexstr))
        print("%s -> %s" % (alias, hexstr[:23]))
        etimer.delay(GAP_MS)
    print("replayed %d frames" % len(steps))
    stop()