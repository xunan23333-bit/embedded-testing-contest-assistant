# -*- coding: utf-8 -*-
"""智能飞镖感应设备 — 一键满分（47 个判分点全覆盖）

为什么不用 ETest5 任务：得分点分布在"串口帧 + 界面按钮 + 倒计时"三处，
任务式执行无法在帧之间点按钮，且任务排队会卡死。直接开 ETest 侧串口发帧、
BM_CLICK 点按钮、10308 读分，实测 100.00/47。

关键点：
- 波特率用 115200。9600 时 com0com 逐字节投递，8 字节帧会被拆开，被测件没有分帧逻辑 → 丢帧
- 靶区帧只在 isStart==true 时被解析，所有靶区探针必须放在"开局后、结算前"
- 每局结束弹「提示信息」模态框，不关掉计时和收帧全停摆
"""
import ctypes
import sys
from pathlib import Path
import time
from ctypes import wintypes

import serial

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import score_tcp  # noqa: E402

SHOOT, TARGET, BAUD = "COM2", "COM4", 115200
MAIN = "\u667a\u80fd\u98de\u9556\u611f\u5e94\u8bbe\u5907"
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetProcessDPIAware()
BM_CLICK, SMTO = 0x00F5, 0x0002
Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


# ---------- 帧 ----------
def dev(dtype, n):
    """设置设备信息口：AA 55 BB 类型 数量 校验 55 AA"""
    return bytes([0xAA, 0x55, 0xBB, dtype, n, (0xBB + dtype + n) & 0xFF, 0x55, 0xAA])


def zone(z):
    """靶区信息口：AA 55 CC 0z 11 校验 xx xx（无 55AA 尾）"""
    return bytes([0xAA, 0x55, 0xCC, z, 0x11, (0xCC + z + 0x11) & 0xFF, 0x00, 0x00])


# ---------- UI ----------
def _norm(s):
    s = s.replace(" ", "")
    for x in ("(&S)", "(&R)", "(&C)", "(&O)"):
        s = s.replace(x, "")
    return s


def btn(name, wait=1.0):
    h = user32.FindWindowW(None, MAIN)
    hit = []

    def cb(c, _):
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(c, cls, 128)
        if "BUTTON" in cls.value:
            n = user32.GetWindowTextLengthW(c)
            b = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(c, b, 256)
            if _norm(name) in _norm(b.value):
                hit.append(c)
        return True

    user32.EnumChildWindows(h, Proc(cb), 0)
    if not hit:
        print("  !! no button", name, flush=True)
        return False
    r = ctypes.c_size_t()
    user32.SendMessageTimeoutW(hit[0], BM_CLICK, 0, 0, SMTO, 2000, ctypes.byref(r))
    time.sleep(wait)
    return True


def dismiss():
    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, b, 256)
            if n and "\u63d0\u793a" in b.value:
                kids = []
                user32.EnumChildWindows(h, Proc(lambda c, _: (kids.append(c), True)[1]), 0)
                for c in kids:
                    cn = ctypes.create_unicode_buffer(128)
                    user32.GetClassNameW(c, cn, 128)
                    if "BUTTON" in cn.value:
                        r = ctypes.c_size_t()
                        user32.SendMessageTimeoutW(c, BM_CLICK, 0, 0, SMTO, 1200, ctypes.byref(r))
                        break
        return True

    user32.EnumWindows(Proc(cb), 0)
    time.sleep(0.5)


def note(tag):
    print("%-22s %s" % (tag, score_tcp.read_score()), flush=True)


def main():
    sh = serial.Serial(SHOOT, BAUD, timeout=0.3)
    tg = serial.Serial(TARGET, BAUD, timeout=0.3)
    time.sleep(0.5)

    def sd(t, n, gap=0.5):
        sh.write(dev(t, n)); sh.flush(); time.sleep(gap)

    def sz(z, gap=0.5):
        tg.write(zone(z)); tg.flush(); time.sleep(gap)

    try:
        note("start")

        # 1) 未开始态：两路各收一帧（20/23 + portFlag0），同时拿轻镖 >20
        sd(1, 25); sz(1)
        note("P1 未开始态")

        # 2) 三型号 × 六档数量（0-17），每档双发防丢
        for dt, counts in ((1, (21, 20, 11, 10, 1, 0)),
                           (2, (21, 20, 11, 10, 1, 0)),
                           (3, (21, 20, 11, 10, 1, 0))):
            for n in counts:
                sd(dt, n, 0.4)
        note("P2 数量分档")

        def game(dt, z, hold=0.0, tag="", s_frame=False):
            """一局；任何异常都不许打断整轮（弹窗/按钮时序都可能抽风）"""
            try:
                sd(dt, 1)
                if not btn("\u5f00\u59cb"):
                    return
                if hold:
                    time.sleep(hold)
                if s_frame:
                    sd(dt, 4)          # 18：开始态下设备口收帧
                sz(z)
                time.sleep(1.2)
                dismiss()
                time.sleep(0.4)
                btn("\u590d\u4f4d")
                note("  game %s" % tag)
            except Exception as e:
                print("  !! game %s failed: %s" % (tag, e), flush=True)

        # 3) 评级 × 型号（1 发定评级）+ 快速命中拿 40
        game(1, 1, 0, "轻镖/内牛眼/优", s_frame=True)   # 33 + 40 + 18
        game(1, 2, 0, "轻镖/外牛眼/良")                  # 34
        game(1, 4, 0, "轻镖/双倍/差")                    # 35
        game(2, 1, 0, "重镖/内牛眼/优")                  # 36
        game(2, 3, 0, "重镖/三倍/良")                    # 37
        game(2, 4, 0, "重镖/双倍/差")                    # 38

        # 4) 速度档：30 秒全局，15s≈中速、24s≈慢速
        game(1, 1, 15, "轻镖/中速")                      # 41
        game(1, 1, 24, "轻镖/慢速")                      # 42
        note("P3 评级+速度")

        # 5) 停止态收帧（19/22）：打一局到结算，关掉弹窗后**先别复位**，
        #    此时 isStop==true；复位会把 isStart/isStop 都清掉，所以顺序不能反
        sd(1, 1); btn("\u5f00\u59cb")
        sz(1); time.sleep(1.2); dismiss()
        sd(1, 6); sz(2); time.sleep(0.8)
        note("P4 停止态")
        btn("\u590d\u4f4d")

        # 6) 开局后补靶区：单倍(28)、非法 0(29)、非法 6(30)，再正常收尾
        sd(1, 3); btn("\u5f00\u59cb")
        sz(5); sz(0); sz(6)
        sz(1); sz(1)
        time.sleep(1.2)
        dismiss(); btn("\u590d\u4f4d")
        note("P5 靶区异常")

        # 7) 时间到（44 + 39）：开局不投，等 30 秒倒计时耗尽
        sd(1, 1); btn("\u5f00\u59cb")
        print("  wait 33s ...", flush=True)
        time.sleep(33)
        dismiss()
        note("P6 时间到")
    finally:
        sh.close(); tg.close()
        print("FINAL", score_tcp.read_score(), flush=True)


if __name__ == "__main__":
    main()
