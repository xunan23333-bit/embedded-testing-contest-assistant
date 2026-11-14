"""Locate the ETest5 installation and the bits that depend on it.

Everything is env-first, then auto-detected, so the same checkout runs on another
machine without editing files.

    ET5_HOME     install root, e.g. D:\\Code\\ETest5
    ET5_PY       interpreter used by the pyserver (default: this interpreter)
    ET5_LOGDIR   engine log root (default: <ET5_HOME>/logs)
    ET5_CDP      Chrome DevTools port for the exam client (default: 9333)

Stdlib only. Import from a script in the same folder:

    from et5env import home, logdir, pyserver_dir, cdp_port
"""
import os
import sys

_CANDIDATES = (
    r"C:\ETest5",
    r"C:\Program Files\ETest5",
    r"C:\Program Files (x86)\ETest5",
    r"D:\Code\ETest5",
    r"D:\ETest5",
)

_cache = {}


def _from_registry():
    """InstallLocation of any uninstall entry whose name mentions ETest."""
    try:
        import winreg
    except ImportError:
        return None
    roots = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
    keys = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
    for root in roots:
        for key in keys:
            try:
                parent = winreg.OpenKey(root, key)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(parent)[0]):
                try:
                    name = winreg.EnumKey(parent, i)
                    sub = winreg.OpenKey(parent, name)
                    display = winreg.QueryValueEx(sub, "DisplayName")[0]
                    if "etest" not in str(display).lower():
                        continue
                    loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                    if loc and os.path.isdir(loc):
                        return os.path.normpath(loc)
                except OSError:
                    continue
    return None


def home():
    """Install root, or None when ETest5 is not installed here."""
    if "home" in _cache:
        return _cache["home"]
    found = os.environ.get("ET5_HOME")
    if found and os.path.isdir(found):
        _cache["home"] = os.path.normpath(found)
        return _cache["home"]
    found = _from_registry()
    if not found:
        for cand in _CANDIDATES:
            if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "ETest5.exe")):
                found = cand
                break
    _cache["home"] = found
    return found


def pyserver_dir():
    root = home()
    if not root:
        return None
    for name in ("pyserver", "node-server", "server"):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            return path
    return root


def logdir():
    explicit = os.environ.get("ET5_LOGDIR")
    if explicit:
        return explicit
    root = home()
    return os.path.join(root, "logs") if root else os.path.join(os.getcwd(), "logs")


def python():
    """Interpreter the pyserver should run under."""
    return os.environ.get("ET5_PY") or sys.executable


def cdp_port():
    return int(os.environ.get("ET5_CDP", "9333"))


def require_home():
    root = home()
    if not root:
        raise SystemExit(
            "ETest5 install not found. Set ET5_HOME, e.g.\n"
            "    set ET5_HOME=D:\\Code\\ETest5\n"
            "Looked for ETest5.exe in: %s" % ", ".join(_CANDIDATES))
    return root


if __name__ == "__main__":
    print("home       :", home() or "(not found)")
    print("pyserver   :", pyserver_dir() or "-")
    print("logs       :", logdir())
    print("python     :", python())
    print("cdp port   :", cdp_port())
