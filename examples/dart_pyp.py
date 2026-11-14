# -*- coding: utf-8 -*-
"""智能飞镖感应设备 —— 满分用例（PYP，在 ETest5 任务里跑）

评分函数（反编译 Frm_Main.getScore）：
    score = Σ portFlags*5 + Σ ifelseFlags*2      # 2 + 45 = 47 个判分点，共 100 分
判分点分布三处：串口帧内容 / 界面按钮 / 一轮结束时的时间与均分。
所以脚本要"发帧 + 让宿主点开始/复位 + 等倒计时"，界面动作由宿主侧
dart_driver.py 代办（PYP 不能点按钮），双方用 dart_cmd.json / dart_ack.json 握手。

判分点 → 触发方式（脚本里的阶段划分）
  P0  空闲态灌 18 帧设备信息
        ifelseFlag0..17 : 轻镖/重镖/未知物 × 数量 (>20,==20,11-19,==10,1-9,==0)
        ifelseFlag20    : 设备口在"未开始"状态收到数据
        ifelseFlag23    : 靶区口在"未开始"状态收到数据
  R1  轻镖1发 内牛眼
        portFlag0/1、18(开始态收设备帧)、21(开始态收靶区帧)、24(内牛眼)、
        31(点开始)、33(轻镖均分>3)、40(快速)、43(剩余=0)
  R2  轻镖4发 三倍/双倍/外牛眼/内牛眼     26 27 25 24；34(轻镖 1<均分<=3)
  R3  轻镖1发 单倍                        28；35(轻镖 均分<=1)
  R4  重镖1发 内牛眼                      36(非轻镖 均分>3)
  R5  重镖1发 外牛眼                      37(非轻镖 1<均分<=3)
  R6  重镖1发 单倍                        38(非轻镖 均分<=1)
  R7  轻镖2发 先非法靶区 0/6 再两发内牛眼  29 30；33
  R8  轻镖1发 不投，等 30s 超时            44(时间归零) 39(无成绩)
  R9  轻镖1发 等 23s 再投                  42(慢速 7/30)
  R10 轻镖1发 等 13s 再投                  41(中速 17/30)
  每轮收尾补：19(停止态收设备帧)、22(停止态收靶区帧)、32(点复位)

踩坑记录（都实测过）：
  * 两边波特率必须 115200。9600 时 com0com 逐字节投递，8 字节帧会拆成 3+5 两次
    DataReceived，被测件没有拼包逻辑，整帧判"无效"。
  * PYP 里 open() 默认 GBK 解码，回执带中文会 UnicodeDecodeError（表现为每条命令
    都等满超时），所以读写都显式 encoding="utf-8"。
  * 靶区帧只在 isStart==true 时解析；靶区探针必须放在"开局后、结算前"。
"""
import json
import time

from etest import etimer, ebuff

CMD = r"C:\path\to\shared\dart_cmd.json"
ACK = r"C:\path\to\shared\dart_ack.json"
PROG = r"C:\path\to\shared\dart_progress.txt"

_seq = [0]


def prog(tag):
    """进度落盘：PYP 的 stdout 看不到，出问题时靠这个定位卡在哪一步"""
    try:
        with open(PROG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), tag))
    except Exception:
        pass


# ------------------------------------------------------------------ 宿主握手
def _next_id():
    # 毫秒时间戳+序号：不要用"读文件里的上个 id 再+1"，两个写方会抢号
    _seq[0] += 1
    return int(time.time() * 1000) * 100 + (_seq[0] % 100)


def sut(op, arg=None, tmo=None):
    """请宿主守护进程点按钮/读界面，返回回执 dict。"""
    cid = _next_id()
    if tmo is None:
        tmo = 60 if op == "wait" else 25
    try:
        with open(CMD, "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": cid, "op": op, "arg": arg or {}}, ensure_ascii=False))
    except Exception as e:
        print("cmd write fail:", e)
        return {"ok": False}
    t0 = time.time()
    while time.time() - t0 < tmo:
        try:
            with open(ACK, encoding="utf-8") as f:
                r = json.loads(f.read())
            if r.get("id") == cid:
                return r
        except Exception:
            pass
        etimer.delay(100)
    print("sut timeout:", op, arg)
    return {"ok": False, "err": "timeout"}


# ------------------------------------------------------------------ 组帧
def dev_frame(dtype, count):
    """设备信息帧：AA 55 BB type number check 55 AA，check=(BB+type+number)&0xFF"""
    return "AA 55 BB %02X %02X %02X 55 AA" % (dtype, count, (0xBB + dtype + count) & 0xFF)


def zone_frame(zone):
    """靶区帧：AA 55 CC zone 11 check 55 AA，check=(CC+zone+11)&0xFF"""
    return "AA 55 CC %02X 11 %02X 55 AA" % (zone, (0xCC + zone + 0x11) & 0xFF)


# ------------------------------------------------------------------ 主流程
def entry(opt=None):
    shoot = channels['COM_shoot']
    target = channels['COM_target']
    for ch in (shoot, target):       # 只用一个通道的任务里，另一个可能没绑定
        if ch is None:
            print("channel missing!")
            stop()
            return

    def send(ch, hexstr, gap=650, drain=None):
        ch.write_buff(ebuff.from_hex(hexstr))
        etimer.delay(gap)
        if drain is not None:
            try:
                drain.read_buff(0, 150)
            except Exception:
                pass

    def finish(dtype, num):
        """一局结算后：停止态各打一帧（19/22），再点复位（32）"""
        send(shoot, dev_frame(dtype, num), 650)
        send(target, zone_frame(1), 650, shoot)
        r = sut("reset")
        if not r.get("ok"):
            sut("close")
            r = sut("reset")
        print("   reset:", r.get("ok"), (r.get("state") or {}).get("state"))

    def run(tag, dtype, num, zones, pre=0, mid_dev=False, tmo=14, blind=0):
        print("== %s type=%d num=%d zones=%s pre=%d ==" % (tag, dtype, num, zones, pre))
        prog("START " + tag)
        send(shoot, dev_frame(dtype, num), 700)
        r = sut("start")
        if not r.get("ok"):
            sut("close")
            sut("reset")
            send(shoot, dev_frame(dtype, num), 700)
            r = sut("start")
        if not r.get("ok"):
            print("   START FAIL", r.get("err"))
            prog("FAIL " + tag + " " + str(r.get("err")))
            return False
        sut("wait", {"field": "state", "eq": "开始投镖", "tmo": 5})
        if mid_dev:                      # 18：开始态下设备口收帧
            send(shoot, dev_frame(dtype, num), 700)
        if pre:
            prog("PRE %s %dms" % (tag, pre))
            etimer.delay(pre)
        for z in zones:
            send(target, zone_frame(z), 700, shoot)
        prog("ARMD " + tag)
        if blind:
            # 倒计时阶段不要一直读界面/点弹窗：实测在"超时结算"那条路上反复读界面
            # 会把被测件搞挂（进程消失、10308 断开），这里干脆闭眼等，只读一次结果
            etimer.delay(blind)
            w = sut("state")
        else:
            w = sut("wait", {"field": "state", "eq": "投镖结束", "tmo": tmo})
        st = w.get("state") or {}
        print("   end state=%s remaining=%s total=%s" % (
            st.get("state"), st.get("remaining"), st.get("total")))
        prog("END %s state=%s rem=%s total=%s" % (tag, st.get("state"),
                                                  st.get("remaining"), st.get("total")))
        finish(dtype, num)
        prog("DONE " + tag)
        return True

    etimer.delay(2500)                   # 暖机：等串口线程稳定

    # 起手复位：上一轮若停在"投镖结束"，设备帧会被 SerialPort_S 直接丢弃
    sut("close")
    r = sut("reset")
    print("== 起手复位:", r.get("ok"), (r.get("state") or {}).get("state"))
    etimer.delay(400)

    # ------------------------------------------------ P0 空闲态值域 0-17
    print("== P0 设备信息六档值域 + 空闲态两个口 ==")
    for dtype in (1, 2, 3):                      # 1轻镖 2重镖 3未知物
        for count in (25, 20, 15, 10, 5, 0):     # >20 ==20 11-19 ==10 1-9 ==0
            send(shoot, dev_frame(dtype, count), 600)
    send(shoot, dev_frame(1, 1), 600)            # 未知物会把"开始"置灰，用轻镖恢复
    send(target, zone_frame(1), 650, shoot)      # 23：靶区口在未开始态收帧

    run("R1 轻镖1发内牛眼", 1, 1, [1], mid_dev=True)
    run("R2 轻镖4发", 1, 4, [3, 4, 2, 1])
    run("R3 轻镖1发单倍", 1, 1, [5])
    run("R4 重镖1发内牛眼", 2, 1, [1])
    run("R5 重镖1发外牛眼", 2, 1, [2])
    run("R6 重镖1发单倍", 2, 1, [5])
    run("R7 轻镖2发非法靶区", 1, 2, [0, 6, 1, 1])
    run("R8 超时无成绩", 1, 1, [], blind=33000)
    run("R9 慢速", 1, 1, [1], pre=23000)
    run("R10 中速", 1, 1, [2], pre=13000)

    send(shoot, dev_frame(1, 1), 600)
    print("ALL DONE")
    stop()
