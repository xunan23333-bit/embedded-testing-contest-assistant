"""Environment doctor: is the ETest5 stack actually usable right now?

    python doctor.py            # report only
    python doctor.py --fix      # start missing pieces via scheduled tasks

Checks: pyserver :9060, node :12123, ETestS5 process, SUT score port :10308,
com0com port pairs, and whether a task is already running in the engine.
Everything here has bitten us at least once; run this before blaming a script.
"""
import argparse
import json
import os
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from et5 import ET5  # noqa: E402
import et5env  # noqa: E402


def _pyserver_task():
    """Command line that starts the pyserver the way the installer does."""
    pdir = et5env.pyserver_dir()
    if not pdir:
        return None
    return ("ETestPyRun",
            'cmd /c "cd /d %s && %s run.py > %s\\pyserver-out.txt 2>&1"'
            % (pdir, et5env.python(), et5env.logdir()))


TASKS = {
    "pyserver": _pyserver_task(),
    "engine": ("ETestS5Run", None),
    "node": ("ETestNodeRun", None),
}
TASKS = {k: v for k, v in TASKS.items() if v}


def port_open(port, host="127.0.0.1", timeout=1.5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def has_proc(name):
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % name],
                             capture_output=True, timeout=20)
        txt = (out.stdout or b"").decode("mbcs", "ignore").lower()
        return name.lower() in txt
    except Exception:
        return False


def run_task(name):
    """Start a scheduled task. schtasks.exe is blacklisted in some sandboxes, so prefer the
    PowerShell cmdlet and only fall back to schtasks."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Start-ScheduledTask -TaskName '%s'" % name],
                           capture_output=True, timeout=40)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    try:
        subprocess.run(["schtasks", "/Run", "/TN", name], capture_output=True, timeout=30)
        return True
    except Exception:
        return False


def active_ports():
    """Only ports that actually exist (pyserial also lists disabled Bluetooth phantoms)."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
        out, i = [], 0
        while True:
            try:
                _, val, _ = winreg.EnumValue(key, i)
                out.append(val)
                i += 1
            except OSError:
                break
        return sorted(out)
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    a = ap.parse_args()

    rows = []

    web = port_open(9060)
    rows.append(("pyserver :9060", web))
    node = port_open(12123)
    rows.append(("node :12123", node))
    eng = has_proc("ETestS5.exe")
    rows.append(("ETestS5.exe", eng))
    score = port_open(10308)
    rows.append(("SUT score :10308", score))

    if a.fix:
        if not web:
            run_task(TASKS["pyserver"][0])
            rows.append(("started pyserver", None))
        if not eng:
            run_task(TASKS["engine"][0])
            rows.append(("started engine", None))
        if not node:
            run_task(TASKS["node"][0])
            rows.append(("started node", None))

    for name, ok in rows:
        mark = "OK  " if ok else ("SKIP" if ok is None else "DOWN")
        print("%-20s %s" % (name, mark))

    if web:
        c = ET5()
        if not c.login():
            print("login: FAILED")
        else:
            print("login: ok")
            r = c.call("POST", "/api/v2/actuator/start_task",
                       {"type": "tsflow", "value": "__probe__", "codes": []})
            msg = str(r.get("msg"))
            if "running" in msg or "\u5df2\u6709\u4efb\u52a1" in msg:
                print("engine: BUSY (a task is stuck; restart ETestS5)")
            else:
                print("engine: idle")

    ports = active_ports()
    print("com ports:", ", ".join(ports) if ports else "(none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
