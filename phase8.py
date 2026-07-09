"""Phase 8 — open-key grouping: the answer is shape, not machinery.

Phase 2 refused open-key group-by because extracting keys from the
rendered thread needs a resident parser (FRICTION.md #10), and predicted
that field-precise queries push toward a different STORED shape (#8).
This phase tests that prediction: the post firing also maintains an
authors-projection chain — one more unsent-instruction chain, written by
the same indivisible firing that stores the message and swaps the thread
head. The "index" is content: demandable, replicable, condensable, owned
by the writer, with no index component anywhere.

Then the unknown key set is itself a query — uniq(sort(demand(authors)))
— and grouping proceeds as in phase 2, with keys the demander just
legitimately learned instead of keys it had to know a priori.

Without the projection (phase-1-shaped data) open-key grouping remains
inexpressible without a parser; that stands as stated. The model's
answer to "unknown keys" is write-side projection.

Run from repo root: python3 phase8.py
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(ROOT, "world8")
PORT = 7841

sys.path.insert(0, ROOT)
from am.instruction import comp, demand, lit
from am.structures import CONCAT, EMIT_DISK, SORT, TALLY, UNIQ
from am.sync import call

NL = lit("\n")


def value(instr):
    kind, v = call("127.0.0.1", PORT, instr)
    assert kind == "value", v
    return v


def start_router():
    p = subprocess.Popen(
        [sys.executable, "-m", "am.router", "--world", WORLD,
         "--port", str(PORT), "--stats", os.devnull],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    import socket
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", PORT), 0.2).close()
            return p
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("router did not come up")


THREAD = "threads/general"
AUTHORS = "threads/general-authors"
seq = [0]


def new_thread():
    value(comp(CONCAT,
               comp(EMIT_DISK, lit("msgs/genesis"), lit(lit(b""))),
               comp(EMIT_DISK, lit(THREAD), lit(lit("msgs/genesis"))),
               comp(EMIT_DISK, lit("auth/genesis"), lit(lit(b""))),
               comp(EMIT_DISK, lit(AUTHORS), lit(lit("auth/genesis")))))


def post(user, text):
    prev_m = value(demand(THREAD)).decode()
    prev_a = value(demand(AUTHORS)).decode()
    n = seq[0]
    seq[0] += 1
    mref, aref = "msgs/%d" % n, "auth/%d" % n
    message = comp(CONCAT, demand(prev_m),
                   lit("[t%02d] %s: %s\n" % (n, user, text)))
    author = comp(CONCAT, demand(prev_a), lit(user + "\n"))
    # message, projection entry, and both head swaps: ONE indivisible firing
    value(comp(CONCAT,
               comp(EMIT_DISK, lit(mref), lit(message)),
               comp(EMIT_DISK, lit(aref), lit(author)),
               comp(EMIT_DISK, lit(THREAD), lit(lit(mref))),
               comp(EMIT_DISK, lit(AUTHORS), lit(lit(aref)))))


def main():
    shutil.rmtree(WORLD, ignore_errors=True)
    router = start_router()
    try:
        new_thread()
        for user, text in [("alice", "hello"), ("bob", "hi"),
                           ("alice", "again"), ("carol", "new here"),
                           ("alice", "third"), ("dave", "me too"),
                           ("carol", "second")]:
            post(user, text)

        # 1. the key set is a query — nobody told the demander who posted
        akey = value(demand(AUTHORS)).decode()
        keys = value(comp(UNIQ, comp(SORT, demand(akey), NL, lit("text")), NL))
        assert keys == b"alice\nbob\ncarol\ndave\n", keys
        print("open keys: PASS — the demander LEARNED the user set from the "
              "projection: %s" % keys.decode().split())

        # 2. group-by over the learned keys, composed as in phase 2
        mkey = value(demand(THREAD)).decode()
        rows = []
        for user in keys.decode().splitlines():
            rows += [lit(user + ": "),
                     comp(TALLY, demand(mkey), NL, lit("] %s: " % user)),
                     lit("\n")]
        table = value(comp(CONCAT, *rows))
        assert table == b"alice: 3\nbob: 1\ncarol: 2\ndave: 1\n", table
        print("open-key group-by: PASS\n" + table.decode())

        # 3. a never-before-seen user appears; no code anywhere knew "eve"
        post("eve", "surprise")
        akey = value(demand(AUTHORS)).decode()
        keys2 = value(comp(UNIQ, comp(SORT, demand(akey), NL, lit("text")), NL))
        assert b"eve" in keys2 and keys2.count(b"\n") == 5
        print("unknown newcomer discovered: PASS (eve)")

        results = dict(keys=keys.decode().split(),
                       table=table.decode().splitlines(),
                       new_structures=["uniq"],
                       projection="authors chain, written by the same firing as the post")
        with open(os.path.join(ROOT, "phase8-results.json"), "w") as f:
            json.dump(results, f, indent=1)
        print("PASS")
        return 0
    finally:
        router.send_signal(signal.SIGTERM)
        router.wait()


if __name__ == "__main__":
    sys.exit(main())
