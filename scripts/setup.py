"""Cold start: import a project zip and print everything you need to wire it up.

    python setup.py import <project.zip>        # upload + import, prints the new pid
    python setup.py info <pid>                  # channels, sequences, COM ports, next steps

Import goes through the same REST pair the UI uses (`project/upload` then `project/import`),
so it works with the web page closed.
"""
import argparse
import json
import os
import sys
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from et5 import ET5  # noqa: E402


def do_import(zip_path):
    c = ET5()
    if not c.login():
        print("login failed")
        return 1
    ws = (((c.call("GET", "api/sys/status").get("data") or {}).get("S")) or {}).get("workspace") or ""
    print("workspace:", ws or "(default)")

    boundary = uuid.uuid4().hex
    fname = os.path.basename(zip_path)
    head = ("--%s\r\nContent-Disposition: form-data; name=\"path\"\r\n\r\n%s/\r\n"
            "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
            "Content-Type: application/zip\r\n\r\n" % (boundary, ws, boundary, fname)).encode()
    payload = head + open(zip_path, "rb").read() + ("\r\n--%s--\r\n" % boundary).encode()

    req = urllib.request.Request(c.base + "/api/v2/project/upload", method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    req.add_header("Authorization", "Bearer " + c.token)
    with urllib.request.urlopen(req, data=payload, timeout=300) as r:
        up = json.loads(r.read().decode("utf-8", "replace"))
    files = (up.get("data") or {}).get("files") or []
    if not files:
        print("upload failed:", json.dumps(up, ensure_ascii=False)[:300])
        return 1

    r2 = c.call("POST", "/api/v2/project/import",
                {"file": files[0], "workspace": ws, "type": "project_import"}, timeout=300)
    if r2.get("code") != 0:
        print("import failed:", json.dumps(r2, ensure_ascii=False)[:300])
        return 1
    d = r2.get("data") or {}
    print("PID: %s" % d.get("project_id"))
    print("NAME: %s" % d.get("project_name"))
    print("\nnext: python setup.py info %s" % d.get("project_id"))
    return 0


def do_info(pid):
    c = ET5()
    if not c.login():
        print("login failed")
        return 1
    c.open(pid)
    ch = c.kv_get(pid, "module.channel") or []
    print("== channels ==")
    for eng in ch:
        for x in eng.get("channels", []):
            p = x.get("port") or {}
            q = x.get("params") or {}
            print("  %-10s %-6s line=%-2s %-5s card=%s" % (
                x.get("name"), p.get("physicalPort"), p.get("line"),
                q.get("baudrate"), (p.get("cardInstanceId") or "")[:8]))
    print("\n== sequences ==")
    for i, s in enumerate(c.sequences(pid), 1):
        print("  %2d %s" % (i, s.get("name")))
    try:
        import serial.tools.list_ports as lp
        print("\n== local COM ports ==")
        for p in lp.comports():
            print("  %-7s %s" % (p.device, p.description))
    except Exception:
        pass
    print("\nnext: python run.py cards / python run.py bind %s Name=COMx ..." % pid)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import"); p.add_argument("zip")
    p = sub.add_parser("info"); p.add_argument("pid")
    a = ap.parse_args()
    return do_import(a.zip) if a.cmd == "import" else do_info(a.pid)


if __name__ == "__main__":
    sys.exit(main())
