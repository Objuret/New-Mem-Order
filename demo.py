# Demo + measurement harness (brief: "Done means" + "Measurements").
#
# This file is test scaffolding, NOT the model: it may use ordinary code,
# JSON (only to build the size-comparison baseline the brief asks for),
# subprocesses and wall-clock waiting. Nothing in here leaks into the
# runtime.
#
# It proves, end to end:
#   1. two clients interact through the router
#   2. the board survives a router restart purely via files that are
#      unsent instructions (no store component exists to recover from)
# and then prints the four measurements.
#
# Usage: python3 demo.py [port] [data_dir]

import json
import os
import shutil
import socket
import subprocess
import sys
import time

import client as cl
import structures
from client import Client
from instruction import value_of

HERE = os.path.dirname(os.path.abspath(__file__))


def start_router(port, data_dir):
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "router.py"), str(port), data_dir])
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            return p
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("router did not come up")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7801
    data_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "data")
    shutil.rmtree(data_dir, ignore_errors=True)

    router = start_router(port, data_dir)
    try:
        # --- two clients interacting -----------------------------------
        alice = Client(port)
        bob = Client(port)

        alice.init_board()
        alice.create_thread("general")
        alice.post("general", "2026-07-07T10:00:00Z", "alice", "hello board")
        bob_view = bob.read("general")
        assert b"alice: hello board" in bob_view, bob_view
        bob.post("general", "2026-07-07T10:01:00Z", "bob", "hi alice")
        alice_view = alice.read("general")
        assert b"alice: hello board" in alice_view and b"bob: hi alice" in alice_view
        index = bob.list_threads()
        assert index == b"general\n", index
        alice.close()
        bob.close()
        print("OK  two clients interacted through the router")

        # --- restart: persistence is nothing but files ------------------
        router.terminate()
        router.wait()
        thread_file = os.path.join(data_dir, "board", "t", "general")
        assert os.path.exists(thread_file), "thread must exist as a plain file"

        router = start_router(port, data_dir)
        carol = Client(port)
        after = carol.read("general")
        assert after == alice_view, (after, alice_view)
        carol.post("general", "2026-07-07T10:05:00Z", "carol", "survived restart")
        assert b"carol: survived restart" in carol.read("general")
        carol.close()
        print("OK  board survived restart via files-as-unsent-instructions")

        # --- measurement 1: structure count -----------------------------
        n_structures = len(structures.REGISTRY)

        # --- measurement 2: repetition ----------------------------------
        with open(os.path.join(data_dir, "firings.log")) as f:
            rows = [line.split("\t") for line in f.read().splitlines()]
        shapes = [r[0] for r in rows]
        invocations = sum(int(r[1]) for r in rows)
        distinct = sorted(set(shapes))

        # --- measurement 3: instruction size vs naive JSON ---------------
        post = cl.post_instr(cl.thread_ref("general"),
                             cl.format_line("2026-07-07T10:01:00Z", "bob", "hi alice"))
        post_json = json.dumps({"op": "post", "thread": "general",
                                "ts": "2026-07-07T10:01:00Z",
                                "author": "bob", "text": "hi alice"}).encode()
        read = cl.read_instr(cl.thread_ref("general"))
        read_json = json.dumps({"op": "read", "thread": "general"}).encode()
        with open(thread_file, "rb") as f:
            stored = f.read()
        content = value_of(stored)

        print()
        print("== MEASUREMENTS ==")
        print(f"1. structure count: {n_structures} "
              f"(terminals: {sum(1 for s in structures.REGISTRY if structures.REGISTRY[s][1])})")
        for sid in sorted(structures.REGISTRY):
            name, term, _ = structures.REGISTRY[sid]
            print(f"   {sid}  {name}{'  [terminal]' if term else ''}")
        print(f"2. repetition: {len(distinct)} distinct compositions / "
              f"{len(shapes)} top-level firings / {invocations} structure invocations")
        for s in distinct:
            print(f"   {shapes.count(s):3d}×  {s}")
        print(f"3. size, post op:  activation {len(post)} B  vs  naive JSON {len(post_json)} B")
        print(f"   size, read op:  activation {len(read)} B  vs  naive JSON {len(read_json)} B")
        print(f"   stored thread file: {len(stored)} B for {len(content)} B of content "
              f"({len(stored) - len(content)} B instruction overhead)")
        print("4. friction log: see friction-log.md")
    finally:
        router.terminate()
        router.wait()


if __name__ == "__main__":
    main()
