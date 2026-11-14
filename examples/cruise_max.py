# 定速巡航系统 — 满分用例（v4）：**跑两遍**才到 100
# 通过 maximize.py 用 --rounds 2 跑，或手动连跑两次同一序列。
# 第一遍通常 94~96，第二遍补上被缓冲区合并/弹窗吞掉的帧。
from etest import etimer, ebuff

S, F2, F1 = 'Speed', 'setting', 'gas'
ACC = "FF 55 02 02 00 00 04 00 FF 55"
DEC = "FF 55 02 02 FF FF 02 02 FF 55"
OPEN = "FF 55 01 02 00 00 03 00 FF 55"
STOP = "FF 55 01 02 FF FF 01 02 FF 55"


def entry(opt=None):
    s, f2, gas = channels[S], channels[F2], channels[F1]

    def send(ch, hexstr, gap=600):
        ch.write_buff(ebuff.from_hex(hexstr))
        etimer.delay(gap)

    def drain():
        try:
            gas.read_buff(0, 120)
        except Exception:
            pass

    etimer.delay(2500)   # 暖机：等串口线程与绑定稳定

    for vhex, ck in (("00 00 80 BF", "4B 01"), ("00 00 00 00", "0C 00"),
                     ("00 00 70 42", "BE 00"), ("00 00 C8 42", "16 01"),
                     ("00 00 F0 42", "3E 01")):
        send(s, "FF 55 08 04 " + vhex + " " + ck + " FF 55", 1200)
        drain()

    for pkt in ("FF 54 08 04 00 00 70 42 BE 00 FF 55",
                "FF 55 08 04 00 00 70 42 BE 00 FF 54",
                "FF 55 08 03 00 00 70 42 BE 00 FF 55",
                "FF 55 07 04 00 00 70 42 BD 00 FF 55",
                "FF 55 08 04 00 00 70 42 00 00 FF 55",
                "AA BB FF 55 08 04 00 00 70 42 BE 00 FF 55"):
        send(s, pkt, 800)
        drain()

    for pkt in ("FF 54 02 02 00 00 04 00 FF 55",
                "FF 55 02 02 00 00 04 00 FF 54",
                "FF 55 02 01 00 00 03 00 FF 55",
                "FF 55 02 02 00 00 00 00 FF 55",
                "11 22 FF 55 02 02 00 00 04 00 FF 55",
                "FF 55 03 02 00 00 05 00 FF 55"):
        send(f2, pkt, 800)

    send(f2, STOP, 1000)
    send(f2, OPEN, 1000)

    send(f2, DEC, 1000)
    send(f2, ACC, 1000)
    for i in range(99):
        send(f2, ACC, 300)
        if i % 25 == 0:
            drain()
    send(f2, ACC, 1000)
    send(f2, ACC, 1000)

    send(s, "00", 2500)
    send(f2, "00", 2500)

    print("done")
    stop()
