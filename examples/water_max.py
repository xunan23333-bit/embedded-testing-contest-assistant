# 人工节奏全量用例：每帧间隔 1.1~1.6s，逐帧排空，覆盖全部 portFlags/ifelseFlags
# 顺序关键：累计推进必须在进程刚启动、累计=0 时先跑
from etest import etimer, ebuff
import struct

def entry(opt=None):
    ch = channels['com']
    st = {'n': 0}

    def drain(n=2):
        for _ in range(n):
            r = ch.read_buff(0, 500)
            if not (isinstance(r, dict) and r.get('value') is not None):
                break

    def wait(i):
        # 1.1~1.6s 交替，模拟人工操作间隔
        d = 1100 + (i % 6) * 100
        etimer.delay(d)

    def send(frame, i, w=None):
        ch.write_buff(ebuff.from_hex(frame.hex()))
        etimer.delay(w if w else (1100 + (i % 6) * 100))
        drain(2)
        st['n'] += 1

    def fr(flow, flag, press, vid=0x11, meter=0x20, h0=0x55, h1=0xAA, t0=0x55, t1=0xAA, bad_ck=False):
        body = bytes([vid & 0xFF, meter & 0xFF]) + struct.pack('<f', flow) + bytes([flag & 0xFF]) + struct.pack('<f', press)
        ck = sum(body) & 0xFFFF
        if bad_ck:
            ck = (ck ^ 0x5555) & 0xFFFF
        return bytes([h0, h1]) + body + struct.pack('<H', ck) + bytes([t0, t1])

    i = 0

    # ===== 阶段1：累计精确推进（必须最先做，此时累计=0）=====
    # 9*500=4500 → +490=4990 → +10=5000 → +1000=6000
    for _ in range(9):
        send(fr(500.0, 1, 3.5), i); i += 1
    send(fr(490.0, 1, 3.5), i); i += 1      # num11=4500
    send(fr(10.0, 1, 3.5), i); i += 1       # num11=4990 → 命中 [4990,5000)
    send(fr(1000.0, 1, 3.5), i); i += 1     # num11=5000 → 命中 ==5000

    # ===== 阶段2：瞬时流量各特殊区间 + 报警阈值（实现为>=400）=====
    for f in (0.5, 0.0, -0.5, 299.5, 300.0, 300.5, 499.5, 500.0, 500.5, 450.0, 400.0):
        send(fr(f, 0, 3.5), i); i += 1

    # ===== 阶段3：管道压力 0~11 全段 =====
    for p in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5,
              5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5,
              9.0, 9.5, 10.0, 10.5, 11.0, -0.5):
        send(fr(100.0, 0, p), i); i += 1

    # ===== 阶段4：输入接口容错 =====
    send(fr(100.0, 1, 3.5, meter=0x21), i); i += 1      # 计费器ID错误
    send(fr(100.0, 1, 3.5, bad_ck=True), i); i += 1     # 校验和错误
    send(fr(100.0, 1, 3.5, h0=0x0C), i); i += 1         # 包头错误
    send(fr(100.0, 1, 3.5, t0=0x0D), i); i += 1         # 包尾错误
    ch.write_buff(ebuff.from_hex('0c'))
    etimer.delay(900)
    drain(1)
    st['n'] += 1

    # ===== 阶段5：粘包 / 半包 =====
    send(fr(320.0, 0, 3.5) + fr(200.0, 0, 2.0), i, 1600); i += 1
    f = fr(150.0, 0, 4.5)
    send(f[:5], i, 900); i += 1
    send(f[5:], i, 1400); i += 1

    # ===== 阶段6：报警与压力联动确认（流量>=400 且压力>4）=====
    send(fr(480.0, 0, 6.5), i); i += 1
    send(fr(120.0, 0, 1.5), i); i += 1
    send(fr(420.0, 1, 5.5), i); i += 1

    print('HUMAN_PACED DONE, frames=%d' % st['n'])
    stop()
