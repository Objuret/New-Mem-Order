"""Phase 5 — the wire. Two worlds, two routers, transfer is activation.

Node A holds the phase-4 world (board, ledgers, promoted shapes). Node B
starts with an empty world and only the universal library. The test:

1. Replicate A's content to B WITHOUT the promoted library. B stores
   everything (opaque values through emits) but firing a condensed chain
   refuses: "unknown structure id N" — the refusal names exactly what
   the receiver lacks.
2. Ship lib/, reload B's router. Every query phase 4 ran against A now
   runs against B, byte-identical. B fires A's instructions natively:
   no format, no negotiation, no import step ever existed.
3. Incremental: one new post on A, delta-sync by mtime. The delta is a
   couple of files of instruction bytes — heads and deltas, as the spec
   predicts traffic should look.

Precondition: world/ populated by phase4.py (run it first if missing).
Run from repo root: python3 phase5.py
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORLD_A = os.path.join(ROOT, "world")
WORLD_B = os.path.join(ROOT, "worldB")
PORT_A, PORT_B = 7821, 7822

sys.path.insert(0, ROOT)
import phase4
from am.instruction import comp, demand, lit
from am.sync import call, sync


def start_router(world, port):
    p = subprocess.Popen(
        [sys.executable, "-m", "am.router", "--world", world,
         "--port", str(port), "--stats", os.devnull],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    import socket
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return p
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("router did not come up on %d" % port)


def stop(p):
    p.send_signal(signal.SIGTERM)
    p.wait()


def queries(port):
    phase4.PORT = port
    return phase4.queries()


def main():
    if not os.path.isdir(os.path.join(WORLD_A, "lib")):
        print("world/ has no promoted lib — run phase4.py first", file=sys.stderr)
        return 1
    shutil.rmtree(WORLD_B, ignore_errors=True)
    os.makedirs(WORLD_B)

    ra = start_router(WORLD_A, PORT_A)
    rb = start_router(WORLD_B, PORT_B)
    try:
        a = queries(PORT_A)

        # 1. content without the dictionary: stored fine, refuses to fire
        full = sync(WORLD_A, "127.0.0.1", PORT_B, lib="skip")
        assert not full["refusals"], full["refusals"]
        phase4.PORT = PORT_B
        thread = phase4.head("threads/general")   # heads are plain literals: fine
        kind, out = call("127.0.0.1", PORT_B, demand(thread))
        assert kind == "error" and b"unknown structure" in out, (kind, out)
        print("bootstrap: B stored %d files (%d wire bytes) and refuses "
              "condensed chains with: %s"
              % (full["files"], full["wire_bytes"], out.decode()))

        # 2. the refusal names the cure: ship lib/, reload B
        libsync = sync(WORLD_A, "127.0.0.1", PORT_B, lib="only")
        assert libsync["files"] > 0 and not libsync["refusals"]
        stop(rb)
        rb = start_router(WORLD_B, PORT_B)
        b = queries(PORT_B)
        assert b == a, "B's answers differ from A's"
        print("replication: PASS (%d lib bytes shipped, router reloaded, "
              "all %d query results from B byte-identical to A)"
              % (libsync["wire_bytes"], len(b)))

        # 3. incremental: one post on A, delta-sync by mtime
        mark = time.time_ns()
        time.sleep(0.01)
        subprocess.run([sys.executable, "-m", "am.client", "post", "general",
                        "alice", "the wire works"], cwd=ROOT, check=True,
                       capture_output=True,
                       env={**os.environ, "AM_PORT": str(PORT_A)})
        delta = sync(WORLD_A, "127.0.0.1", PORT_B, since_ns=mark, lib="skip")
        assert not delta["refusals"]
        board_a = queries(PORT_A)["board"]
        board_b = queries(PORT_B)["board"]
        assert board_b == board_a and b"the wire works" in board_b
        print("incremental: PASS (%d files, %d wire bytes — an uncondensed "
              "new message interoperates with no reload)"
              % (delta["files"], delta["wire_bytes"]))

        # labeled anecdote (brief: optional comparisons): the same logical
        # data as minimal JSON
        anecdote = len(json.dumps({
            "posts": [line for line in board_a.decode().splitlines() if line],
            "ledgers": phase4.LEDGERS, "budgets": phase4.BUDGETS,
        }).encode())
        results = dict(
            full_sync=dict(files=full["files"], wire_bytes=full["wire_bytes"],
                           content_bytes=full["content_bytes"]),
            lib_sync=dict(files=libsync["files"], wire_bytes=libsync["wire_bytes"]),
            delta_sync=dict(files=delta["files"], wire_bytes=delta["wire_bytes"]),
            json_anecdote_bytes=anecdote,
            queries_identical=True,
        )
        with open(os.path.join(ROOT, "phase5-results.json"), "w") as f:
            json.dump(results, f, indent=1)
        print("full sync: %d files, %d wire bytes (%d stored-instruction "
              "bytes); JSON of the same logical data (labeled anecdote): %d"
              % (full["files"], full["wire_bytes"], full["content_bytes"],
                 anecdote))
        print("PASS")
        return 0
    finally:
        stop(ra)
        stop(rb)


if __name__ == "__main__":
    sys.exit(main())
