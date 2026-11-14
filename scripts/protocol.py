"""Read a project's protocol definitions and emit ready-to-send frames.

Protocol definitions live in the project export, not in project_kv, so this tool
exports the project, parses `tables.protocol`, and packs frames with the same field
order the engine uses (integer width/endianness, float32 payload, CheckCode(SUM_8)).

    python protocol.py <pid> --list
    python protocol.py <pid> --pack P_speed speed=60
    python protocol.py <pid> --pack P_setting cmdType=1 dataValue=0
    python protocol.py <pid> --examples          # one sample frame per protocol

Field values not supplied fall back to the item's `autoValue` (header/tail/length are
usually right by default). Checksums are always recomputed.
"""
import argparse
import json
import os
import re
import struct
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from et5 import ET5  # noqa: E402
import submit  # noqa: E402


def load_tables(pid):
    tmp = os.path.join(tempfile.gettempdir(), "et5_proto_%s.zip" % pid[:8])
    rc = submit.export(pid, tmp)
    if rc != 0 or not os.path.exists(tmp):
        return None
    with zipfile.ZipFile(tmp) as z:
        names = [n for n in z.namelist() if n.startswith("project_") and n.endswith(".json")]
        if not names:
            return None
        data = json.loads(z.read(names[0]).decode("utf-8", "replace"))
    return data.get("tables") or {}


def int_auto(expr):
    if not expr:
        return 0
    expr = str(expr).strip()
    try:
        return int(expr, 0)
    except ValueError:
        return 0


def to_bytes(item, value):
    kind = item.get("kind")
    big = str(item.get("bigOrder", "false")).lower() == "true"
    if kind == "seg_real":
        return struct.pack(">f" if big else "<f", float(value))
    bits = int(item.get("bitCount") or 8)
    n = max(1, bits // 8)
    v = int(value) & ((1 << bits) - 1)
    return v.to_bytes(n, "big" if big else "little")


def pack(proto, values):
    d = proto.get("data")
    if isinstance(d, str):
        d = json.loads(d)
    items = (d or {}).get("items") or []
    chunks = []
    field_bytes = {}
    body_sum = 0
    for it in items:
        name = it.get("name")
        kind = it.get("kind")
        if kind == "checknum" or "CheckCode" in str(it.get("autoValue") or ""):
            continue
        if name in values:
            raw = values[name]
        else:
            raw = it.get("autoValue")
            if kind == "seg_real":
                raw = 0.0 if raw in (None, "") else float(raw)
            else:
                raw = int_auto(raw)
        b = to_bytes(it, raw)
        field_bytes[name] = b
        chunks.append(b)
        if name not in ("header", "tail"):
            body_sum += sum(b)

    total_len = sum(len(c) for c in chunks) - 4  # minus header+tail, matches typical dataLen
    out = b""
    for it in items:
        name = it.get("name")
        kind = it.get("kind")
        if kind == "checknum" or "CheckCode" in str(it.get("autoValue") or ""):
            # engine's SUM_8 covers cmdType + dataLen + payload (everything between header
            # and the checksum), even when the autoValue expression lists fewer fields
            v = body_sum & 0xFF
            bits = int(it.get("bitCount") or 16)
            n = max(1, bits // 8)
            big = str(it.get("bigOrder", "false")).lower() == "true"
            out += v.to_bytes(n, "big" if big else "little")
        else:
            out += field_bytes[name]
    return out.hex(" ").upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--pack")
    ap.add_argument("--examples", action="store_true")
    ap.add_argument("kv", nargs="*", help="field=value pairs for --pack")
    a = ap.parse_args()

    tables = load_tables(a.pid)
    if not tables:
        print("cannot read project export")
        return 1

    protos = {r.get("name"): r for r in (tables.get("protocol") or [])}
    print("protocols:", ", ".join(sorted(protos)) or "(none)")

    if a.list or not (a.pack or a.examples):
        for name, p in sorted(protos.items()):
            data = p.get("data")
            data = json.loads(data) if isinstance(data, str) else data
            items = data.get("items", [])
            print("\n%s  (%d fields)" % (name, len(items)))
            for it in items:
                print("   %-10s %-12s bits=%-4s %s" % (it.get("name"), it.get("kind"),
                                                       it.get("bitCount"), it.get("autoValue")))
        return 0

    if a.examples:
        for name in sorted(protos):
            print("%-10s %s" % (name, pack(protos[name], {})))

    if a.pack:
        proto = protos.get(a.pack)
        if not proto:
            print("no such protocol:", a.pack)
            return 1
        vals = {}
        for kv in a.kv:
            if "=" in kv:
                k, v = kv.split("=", 1)
                vals[k] = float(v) if "." in v else int(v, 0)
        print(pack(proto, vals))
    return 0


if __name__ == "__main__":
    sys.exit(main())

