"""Instant score read straight from the SUT's built-in TCP score service.

Most instrumented SUTs listen on 10308 and answer a query frame with
`FF FF 04 <double LE score> ...`, which is far faster and more stable than driving
the exam-client UI. Falls back to nothing if the port is closed.

    python score_tcp.py [--port 10308] [--host 127.0.0.1]
"""
import argparse
import socket
import struct
import sys


QUERIES = (b"\xff\xff\x01\xf0", b"\xff\xff\x01\x0f")


def _try(host, port, head, timeout):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.sendall(head + struct.pack("<f", 1.4))
        buf = b""
        while len(buf) < 17:
            chunk = s.recv(64)
            if not chunk:
                break
            buf += chunk
    except Exception:
        return None
    finally:
        s.close()
    if len(buf) < 11:
        return None
    try:
        return struct.unpack("<d", buf[3:11])[0]
    except Exception:
        return None


def read_score(host="127.0.0.1", port=10308, timeout=3.0):
    """Try each known query header; the two problems so far used F0 and 0F."""
    for head in QUERIES:
        v = _try(host, port, head, timeout)
        if v is not None and v >= 0:
            return v
    for head in QUERIES:
        v = _try(host, port, head, timeout)
        if v is not None:
            return v
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=10308)
    a = ap.parse_args()
    sc = read_score(a.host, a.port)
    if sc is None:
        print("SCORE_TCP: unavailable")
        return 1
    print("SCORE_TCP: %.2f" % sc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
