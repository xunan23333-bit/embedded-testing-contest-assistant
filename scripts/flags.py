"""从被测件 10308 端口读全部判分点状态（比分数有用得多）。

FF FF 01 0F + float32(1.4)  ->  FF FF <int32 len> <json> <uint32 caseid>
json 是 [{"nodeName":"portFlag0","category":"portFlag","ifCatch":true}, ...]
"""
import json
import socket
import struct
import sys

HOST, PORT = "127.0.0.1", 10308


def fetch(timeout=3.0):
    s = socket.socket()
    s.settimeout(timeout)
    s.connect((HOST, PORT))
    s.sendall(b"\xff\xff\x01\x0f" + struct.pack("<f", 1.4))
    buf = b""
    while len(buf) < 6:
        c = s.recv(65536)
        if not c:
            break
        buf += c
    if len(buf) < 6:
        s.close()
        return None
    n = struct.unpack("<i", buf[2:6])[0] - 4
    while len(buf) < 6 + n:
        c = s.recv(65536)
        if not c:
            break
        buf += c
    s.close()
    js = buf[6:6 + n].decode("utf-8", "replace")
    return json.loads(js)


def main():
    nodes = fetch()
    if nodes is None:
        print("unavailable")
        return 1
    got = [x["nodeName"] for x in nodes if x.get("ifCatch")]
    miss = [x["nodeName"] for x in nodes if not x.get("ifCatch")]
    print("total=%d caught=%d  score=%.2f" % (len(nodes), len(got), len(got) * 0 + sum(
        5 if x["category"] == "portFlag" else 2 for x in nodes if x.get("ifCatch"))))
    print("MISS:", " ".join(miss) if miss else "(none)")
    print("GOT :", " ".join(got))
    return 0


if __name__ == "__main__":
    sys.exit(main())
