"""Hostile-input tests, chartered by the external review (2026-07-11,
CRITICAL-REVIEW.md finding #7): the claim "always fires or refuses"
must hold against inputs that are malformed, legal-but-absurd, or
corrupt at rest. Every case must produce an error frame / errno, and
the router must survive to answer a good instruction afterwards.

Run from repo root: python3 robustness_tests.py
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "robustness")
PORT = 7971

sys.path.insert(0, ROOT)
from am.instruction import Incomplete, comp, demand, lit, outcome, skip
from am.structures import CONCAT
from am.layer import Layer, LayerError


def call_fresh(payload):
    """One connection, one payload, read one frame (or closed)."""
    with socket.create_connection(("127.0.0.1", PORT), 2) as s:
        s.sendall(payload)
        s.settimeout(5)
        buf = b""
        while True:
            try:
                end = skip(buf, 0)
                return outcome(buf[:end])
            except Incomplete:
                pass
            data = s.recv(65536)
            if not data:
                return ("closed", b"")
            buf += data


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    world = os.path.join(WORK, "world")
    proc = subprocess.Popen(
        [sys.executable, "-m", "am.router", "--world", world,
         "--port", str(PORT), "--stats", os.devnull],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", PORT), 0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    try:
        # 1. NUL byte inside a demand reference: refusal, not ValueError
        k, v = call_fresh(demand(b"a\x00b"))
        assert k == "error" and b"bad reference" in v, (k, v)
        print("NUL-byte reference        -> refused (%r)" % v[:40])

        # 2. legal but 60,000-deep nesting: refusal, not RecursionError
        deep = lit(b"x")
        for _ in range(60000):
            deep = comp(CONCAT, deep)
        k, v = call_fresh(deep)
        assert k == "error" and b"deep" in v, (k, v)
        print("60k-deep legal nesting    -> refused (%r)" % v[:40])

        # 3. garbage tag: refused (pre-existing behavior, pinned)
        k, v = call_fresh(b"\x09garbage")
        assert k == "error", (k, v)
        print("garbage bytes             -> refused (%r)" % v[:40])

        # 4. traversal: refused (pre-existing behavior, pinned)
        k, v = call_fresh(demand(b"../secrets"))
        assert k == "error" and b"bad reference" in v, (k, v)
        print("path traversal            -> refused (%r)" % v[:40])

        # 5. the router is still alive and still fires
        k, v = call_fresh(comp(CONCAT, lit(b"still "), lit(b"alive")))
        assert (k, v) == ("value", b"still alive"), (k, v)
        print("router after all of it    -> fires (%r)" % v)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait()

    # 6. corrupt/short head at rest: EIO through the layer, not a crash
    store = os.path.join(WORK, "store")
    layer = Layer(store, cache=False)
    layer.put("f", b"hello")
    head_path = os.path.join(store, "fs", "f")
    with open(head_path, "wb") as f:
        f.write(lit(b"reg\n"))          # one field instead of five
    try:
        layer.getattr("f")
        raise AssertionError("short head did not raise")
    except LayerError as e:
        import errno as errno_mod
        assert e.errno == errno_mod.EIO, e.errno
        print("corrupt short head        -> EIO")

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
