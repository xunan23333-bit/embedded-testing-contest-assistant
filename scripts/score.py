"""Read the local score from ETest5's third-party exam client (no token needed).

Requires a persistent Edge/Chrome with remote debugging (see SKILL.md), because
Playwright-launched browsers render the ETest5 SPA blank.

    python score.py                 # offline mode, print score
    python score.py --shot a.png    # also save screenshot
    python score.py --cdp 9333 --wait 12
"""
import argparse
import os
import re
import sys
import time

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = os.environ.get("ET5_BASE", "http://localhost:9060")


def body(pg):
    return pg.evaluate("() => document.body.innerText") or ""


def login_if_needed(pg):
    t = body(pg)
    if "第三方考试客户端" in t:
        return True
    vis = [i for i in range(pg.locator("input").count()) if pg.locator("input").nth(i).is_visible()]
    if len(vis) >= 2:
        pg.locator("input").nth(vis[0]).fill("admin")
        pg.locator("input").nth(vis[1]).fill("123456")
        try:
            pg.get_by_role("button", name=re.compile("登")).first.click()
        except Exception:
            pg.keyboard.press("Enter")
        pg.wait_for_timeout(7000)
        return "第三方考试客户端" in body(pg)
    return False


def open_client(pg):
    pg.evaluate("() => { location.hash = '#/third-party-test'; }")
    pg.wait_for_timeout(4000)
    return "第三方考试客户端" in body(pg)


def offline_on(pg):
    sw = pg.locator(".ant-switch").first
    if not sw.count():
        return False
    cls = sw.get_attribute("class") or ""
    if "checked" not in cls:
        sw.click()
        pg.wait_for_timeout(1200)
    return True


def read_score(pg, wait_s=10):
    for name in ("读取本地分数", "从本地程序获取分数"):
        btn = pg.get_by_role("button", name=re.compile(name)).first
        if btn.count():
            btn.click()
            break
    t0 = time.time()
    while time.time() - t0 < wait_s:
        pg.wait_for_timeout(1000)
        m = re.search(r"当前得分\s*\n?\s*([0-9]{1,3}(?:\.[0-9]+)?)", body(pg))
        if m:
            return float(m.group(1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="9333")
    ap.add_argument("--shot")
    ap.add_argument("--wait", type=int, default=12)
    a = ap.parse_args()

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:%s" % a.cdp)
        ctx = b.contexts[0] if b.contexts else b.new_context()
        pg = next((x for x in ctx.pages if "9060" in x.url), None)
        if pg is None:
            pg = ctx.new_page()
            pg.goto(BASE + "/index.html", wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
        pg.bring_to_front()

        if not login_if_needed(pg):
            if not open_client(pg):
                if not login_if_needed(pg) or not open_client(pg):
                    print("!! cannot reach exam client")
                    print(body(pg)[:300])
                    return 1
        offline_on(pg)
        sc = read_score(pg, a.wait)
        print("SCORE:", "%.2f" % sc if sc is not None else "None")
        if a.shot:
            pg.screenshot(path=a.shot)
            print("shot:", a.shot)
        if sc is None:
            print(body(pg)[-400:].replace("\n", " | "))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
