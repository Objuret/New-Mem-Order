"""End-to-end demonstration against the brief's 'done means':

message board runs, two clients post and read through the router, an
error path refuses cleanly, and the board survives a router restart with
nothing but files-as-unsent-instructions carrying the state.

Run from the repo root: python3 demo.py
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(ROOT, "world")
STATS = os.path.join(ROOT, "stats.log")
PORT = "7799"


def start_router():
    p = subprocess.Popen(
        [sys.executable, "-m", "am.router", "--world", WORLD,
         "--stats", STATS, "--port", PORT],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", int(PORT)), 0.2).close()
            return p
        except OSError:
            time.sleep(0.05)
    p.kill()
    raise RuntimeError("router did not come up")


def client(*args, expect=0):
    r = subprocess.run(
        [sys.executable, "-m", "am.client", *args],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "AM_PORT": PORT})
    if r.returncode != expect:
        raise AssertionError(
            "client %r exited %d (expected %d)\nstdout: %s\nstderr: %s"
            % (args, r.returncode, expect, r.stdout, r.stderr))
    return r.stdout if expect == 0 else r.stderr


def main():
    shutil.rmtree(WORLD, ignore_errors=True)
    if os.path.exists(STATS):
        os.remove(STATS)

    router = start_router()
    try:
        client("new-thread", "general")
        client("post", "general", "alice", "hello bob")
        time.sleep(0.002)  # distinct millisecond message ids
        client("post", "general", "bob", "hi alice, reading you through the router")
        time.sleep(0.002)
        client("post", "general", "alice", "let's see if this survives a restart")
        before = client("read", "general")
        print(before)

        missing = client("read", "nowhere", expect=1)
        assert "no such reference" in missing, missing
        print("refusal on a missing reference: OK")
    finally:
        router.send_signal(signal.SIGTERM)
        router.wait()

    router = start_router()
    try:
        after = client("read", "general")

        assert before == after, ("thread changed across restart:\n%s\n%s"
                                 % (before, after))
        for expected in ("hello bob", "hi alice", "survives a restart",
                         "=== thread general ==="):
            assert expected in after, "missing %r in thread" % expected
        print("restart survival: OK (thread identical, state carried only by files)")

        # Phase 2: the three queries, over the phase-1 data that survived
        # the restart. Conditions are values inside the instructions.
        found = client("find", "general", "restart")
        assert found.count("\n") == 1 and "survives a restart" in found, found
        empty = client("find", "general", "no such text anywhere")
        assert empty == "", repr(empty)
        print("find: OK\n" + found)

        counts = client("count", "general", "alice", "bob", "eve")
        assert counts == "alice: 2\nbob: 1\neve: 0\n", repr(counts)
        print("count: OK\n" + counts)

        newest = client("newest", "general", "2")
        lines = newest.splitlines()
        assert len(lines) == 2, newest
        assert "hi alice" in lines[0] and "survives a restart" in lines[1], newest
        print("newest 2: OK\n" + newest)
    finally:
        router.send_signal(signal.SIGTERM)
        router.wait()

    print("PASS")


if __name__ == "__main__":
    main()
