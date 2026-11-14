"""Export the project result ZIP and (optionally) push it through the exam client.

    python submit.py export <pid> out.zip
    python submit.py upload out.zip <token> [--cdp 9333] [--shot s.png]

Export is pure REST (no UI). Upload drives ETest5's third-party exam client over CDP:
read score -> verify -> pick ZIP -> upload & write back -> confirm. The platform keeps
only the LAST submission, so submit early and often.

Zip is capped at 50 MB by the platform; a normal project lands around 7-8 MB.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from et5 import ET5  # noqa: E402

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"


def export(pid, out):
    c = ET5()
    if not c.login():
        print("login failed")
        return 1
    c.open(pid)
    ws = (((c.call("GET", "api/sys/status").get("data") or {}).get("S")) or {}).get("workspace") or ""
    r = c.call("POST", "/api/v2/project/%s/export" % pid,
               {"workspace": ws, "type": "project_export", "is_all": 1}, timeout=180)
    d = r.get("data")
    path = d if isinstance(d, str) else (d or {}).get("file")
    if not path:
        print("export failed:", json.dumps(r, ensure_ascii=False)[:300])
        return 1
    url = c.base + urllib.parse.quote(path, safe="/?=&:")
    req = urllib.request.Request(url)
    if c.token:
        req.add_header("Authorization", "Bearer " + c.token)
    blob = urllib.request.urlopen(req, timeout=180).read()
    open(out, "wb").write(blob)
    print("SAVED %s  %.2f MB  magic=%r" % (out, len(blob) / 1048576, blob[:2]))
    return 0


def upload(zip_path, token, cdp, shot):
    from playwright.sync_api import sync_playwright

    def body(pg):
        return pg.evaluate("() => document.body.innerText") or ""

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:%s" % cdp)
        ctx = b.contexts[0]
        pg = next((x for x in ctx.pages if "9060" in x.url), ctx.new_page())
        pg.bring_to_front()

        if "第三方考试客户端" not in body(pg):
            vis = [i for i in range(pg.locator("input").count()) if pg.locator("input").nth(i).is_visible()]
            if len(vis) >= 2:
                pg.locator("input").nth(vis[0]).fill("admin")
                pg.locator("input").nth(vis[1]).fill("123456")
                pg.get_by_role("button", name=re.compile("登")).first.click()
                pg.wait_for_timeout(6000)
            pg.evaluate("() => { location.hash = '#/third-party-test'; }")
            pg.wait_for_timeout(4000)

        box = pg.locator("input[placeholder*='secret'], input[placeholder*='令牌']").first
        if box.count():
            box.fill(token)
            btn = pg.get_by_role("button", name=re.compile("验证")).first
            if btn.count():
                btn.click()
                pg.wait_for_timeout(7000)
        t = body(pg)
        if "\u961f\u4f0d" not in t:
            print("token not verified:", t[:300].replace("\n", " | "))
            return 1

        for label, wait in (("\u4ece\u672c\u5730\u7a0b\u5e8f\u83b7\u53d6\u5206\u6570", 9000),
                            ("\u6821\u9a8c\u672c\u5730\u7ed3\u679c", 6000)):
            btn = pg.get_by_role("button", name=re.compile(label)).first
            if btn.count():
                btn.click()
                pg.wait_for_timeout(wait)
        m = re.search(r"当前得分\s*\n?\s*([0-9]{1,3}(?:\.[0-9]+)?)", body(pg))
        print("score:", m.group(1) if m else "?", flush=True)

        pg.locator("input[type='file']").first.set_input_files(zip_path)
        pg.wait_for_timeout(4000)
        for label, wait in (("\u4e0a\u4f20\u5e76\u56de\u5199", 6000), ("\u786e\u8ba4\u56de\u5199", 12000)):
            btn = pg.get_by_role("button", name=re.compile(label)).first
            if btn.count():
                btn.click()
                pg.wait_for_timeout(wait)
        t = body(pg)
        ok = any(k in t for k in ("上传成功", "回写成功", "结果包上传成功"))
        print("RESULT:", "SUBMITTED" if ok else "CHECK_MANUALLY")
        print(t[:400].replace("\n", " | "))
        if shot:
            pg.screenshot(path=shot)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export"); p.add_argument("pid"); p.add_argument("out")
    p = sub.add_parser("upload"); p.add_argument("zip"); p.add_argument("token")
    p.add_argument("--cdp", default="9333"); p.add_argument("--shot")
    a = ap.parse_args()
    if a.cmd == "export":
        return export(a.pid, a.out)
    return upload(a.zip, a.token, a.cdp, a.shot)


if __name__ == "__main__":
    sys.exit(main())
