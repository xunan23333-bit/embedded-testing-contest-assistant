"""Decompile a .NET SUT and surface its scoring hooks — the highest-value 5 minutes.

    python decompile.py "<SUT.exe>" [-o outdir]
    python decompile.py "<SUT.exe>" --grep        # after decompiling, print scoring summary

Needs: dotnet SDK + `dotnet tool install -g ilspycmd` (once).
If the binary is obfuscated/packed, fall back to `--strings` (UTF-16 literals still leak
log messages, which reveal branches).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

PATTERNS = ["getScore", "Flags", "score", "Score", "coverage", "ifelseFlags", "portFlags"]


def find_ilspy():
    for p in (os.path.expanduser(r"~\.dotnet\tools\ilspycmd.exe"),
              shutil.which("ilspycmd"),
              shutil.which("ilspycmd.exe")):
        if p and os.path.exists(p):
            return p
    return ""


def strings(path, limit=400):
    data = open(path, "rb").read()
    ascii_s = re.findall(rb"[\x20-\x7e]{6,80}", data)
    utf16 = re.findall(rb"(?:[\x20-\x7e]\x00){4,80}", data)
    out = []
    for s in ascii_s + utf16:
        try:
            t = s.decode("utf-16-le" if b"\x00" in s else "ascii", "ignore").strip()
        except Exception:
            continue
        if t and t not in out:
            out.append(t)
    return out[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe")
    ap.add_argument("-o", "--out")
    ap.add_argument("--grep", action="store_true")
    ap.add_argument("--strings", action="store_true")
    a = ap.parse_args()

    if a.strings:
        for s in strings(a.exe):
            print(s)
        return 0

    out = a.out or os.path.join(os.getcwd(), "decompiled")
    os.makedirs(out, exist_ok=True)
    ilspy = find_ilspy()
    if not ilspy:
        print("ilspycmd not found. Install: dotnet tool install -g ilspycmd --version 8.2.0.7535")
        return 1
    print("decompiling ->", out)
    r = subprocess.run([ilspy, "-o", out, "--nested-directories", a.exe],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout or "")[-400:])
    if r.returncode != 0:
        print((r.stderr or "")[-600:])
        return 1

    files = []
    for root, _, names in os.walk(out):
        for n in names:
            if n.endswith(".cs"):
                files.append(os.path.join(root, n))
    print("cs files:", len(files))

    if a.grep:
        for f in files:
            src = open(f, encoding="utf-8", errors="replace").read()
            hits = [ln.strip() for ln in src.splitlines()
                    if any(p in ln for p in ("getScore", "Flags[", "score"))]
            if hits:
                print("\n###", os.path.basename(f))
                for h in hits[:40]:
                    print("   ", h[:160])
    return 0


if __name__ == "__main__":
    sys.exit(main())
