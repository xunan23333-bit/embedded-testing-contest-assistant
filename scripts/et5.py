"""ETest5 REST client + sequence runner (stdlib only).

No third-party deps. Works against the local ETest5 pyserver (default :9060).

    from et5 import ET5
    c = ET5(); c.login(); c.open(PID)
    c.kv_get(PID, "module.channel")
"""
import glob
import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = os.environ.get("ET5_BASE", "http://localhost:9060")
USER = os.environ.get("ET5_USER", "admin")
PWD = os.environ.get("ET5_PWD", "123456")

try:
    from et5env import logdir as _logdir
    LOGDIR = _logdir()
except Exception:                                     # keep the module importable alone
    LOGDIR = os.environ.get("ET5_LOGDIR", os.path.join(os.getcwd(), "logs"))


class ET5:
    def __init__(self, base=BASE, user=USER, pwd=PWD):
        self.base = base.rstrip("/")
        self.user = user
        self.pwd = pwd
        self.token = ""

    # ---------- transport ----------
    def call(self, method, path, body=None, timeout=30):
        if not path.startswith("/"):
            path = "/" + path
        req = urllib.request.Request(self.base + path, method=method.upper())
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            return {"code": e.code, "msg": e.read().decode("utf-8", "replace")[:300]}
        except Exception as e:
            return {"code": -1, "msg": str(e)[:300]}

    # ---------- session ----------
    def login(self):
        r = self.call("POST", "/api/v2/user/login_and_auth",
                      {"username": self.user, "password": self.pwd, "app": "ET5", "proj_id": ""})
        d = r.get("data") or {}
        self.token = (r.get("token") or r.get("access_token")
                      or (d.get("token") if isinstance(d, dict) else "")
                      or d.get("accessToken") or d.get("access_token") or "")
        return bool(self.token)

    def open(self, pid):
        return self.call("POST", "/api/v2/ctrl/project/open", {"proj_id": pid})

    # ---------- project ----------
    def projects(self):
        r = self.call("GET", "/api/v2/project/all?searchKeyword=&searchScopes=name&pageSize=50&current=1")
        return ((r.get("data") or {}).get("list")) or []

    def sequences(self, pid):
        r = self.call("GET", "/api/v2/sequence/list?pid=%s&current=1&pageSize=200" % pid)
        return ((r.get("data") or {}).get("list")) or []

    def detail(self, pid, sid):
        return (self.call("GET", "/api/v2/sequence/detail?id=%s&pid=%s" % (sid, pid)).get("data")) or {}

    def kv_get(self, pid, key):
        d = self.call("GET", "/api/v2/project_kv/detail?pid=%s&key=%s" % (pid, key)).get("data")
        return json.loads(d) if isinstance(d, str) else d

    def kv_set(self, pid, key, value):
        return self.call("POST", "/api/v2/project_kv/update?pid=%s&key=%s" % (pid, key), value)

    # ---------- run ----------
    def start(self, pid, sid):
        d = self.detail(pid, sid)
        return self.call("POST", "/api/v2/actuator/start_task",
                         {"type": "tsflow", "value": sid, "codes": d.get("codes") or []}, timeout=40)

    def stop(self, task_id):
        return self.call("POST", "/api/ctrl/stop_task/%s" % task_id, {})

    @staticmethod
    def latest_log():
        pats = [os.path.join(LOGDIR, "2026_*", "S0_*.txt"), os.path.join(LOGDIR, "*", "S0_*.txt")]
        files = []
        for p in pats:
            files += glob.glob(p)
        return max(files, key=os.path.getmtime) if files else ""

    def wait(self, timeout=300, poll=2.0, log=None):
        """Tail engine log for `task run result = ...`."""
        log = log or self.latest_log()
        if not log:
            return "NO_LOG"
        pos = os.path.getsize(log)
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(poll)
            try:
                with open(log, encoding="utf-8", errors="ignore") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
            except OSError:
                continue
            m = re.findall(r"task run result = (\w+)", chunk)
            if m:
                return m[-1]
        return "TIMEOUT"

    def run(self, pid, sid, timeout=300, verbose=True):
        r = self.start(pid, sid)
        if r.get("code") != 0:
            return "START_FAIL: " + str(r.get("msg"))
        tid = (r.get("data") or {}).get("task_id")
        if verbose:
            print("   task", tid, flush=True)
        return self.wait(timeout=timeout)


def main():
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        return
    c = ET5()
    if not c.login():
        print("login failed")
        return
    cmd = sys.argv[1]
    if cmd == "projects":
        for p in c.projects():
            print("%-40s %s" % (p.get("id"), p.get("name")))
    elif cmd == "seqs":
        pid = sys.argv[2]
        c.open(pid)
        for i, s in enumerate(c.sequences(pid), 1):
            print("%2d  %-40s %s" % (i, s.get("name"), s.get("id")))
    elif cmd == "log":
        print(c.latest_log())


if __name__ == "__main__":
    main()
