"""Phase 7 — multi-writer without coordination: merge is a query.

Two nodes, two writers. Alice posts only on node A, bob only on node B;
each writer swaps only its OWN head, so no head ever has two writers
and the phase-1 lost-update window never opens between them. Sync
(phase 5) exchanges the chains — references are disjoint by
construction. A merged thread is not stored anywhere: it is an
instruction, sort∘concat over both demanded chains, fired at read time.
Because rendering is deterministic, both nodes fire the same merge
instruction over the same replicated data and get byte-identical
results — convergence with zero coordination machinery, no new
structures, no grammar change.

Chronology rides in the rendered line prefix ("[YYYY-mm-dd HH:MM:SS.mmm]"),
a convention owned by this workload's posts (phase-2 ruling: record
conventions are the demander's, entering as values).

Run from repo root: python3 phase7.py
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WA = os.path.join(ROOT, "world7a")
WB = os.path.join(ROOT, "world7b")
PA, PB = 7831, 7832

sys.path.insert(0, ROOT)
from am.instruction import comp, demand, lit
from am.structures import CONCAT, EMIT_DISK, LAST, SELECT, SORT
from am.sync import call, sync

NL = lit("\n")


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
    raise RuntimeError("router did not come up")


def value(port, instr):
    kind, v = call("127.0.0.1", port, instr)
    assert kind == "value", v
    return v


class Writer:
    """One user, one node, one head — the single-writer discipline."""

    def __init__(self, user, port):
        self.user = user
        self.port = port
        self.head = "threads/general-" + user
        self.seq = 0
        genesis = "msgs/%s-genesis" % user
        value(port, comp(CONCAT,
                         comp(EMIT_DISK, lit(genesis), lit(lit(b""))),
                         comp(EMIT_DISK, lit(self.head), lit(lit(genesis)))))

    def post(self, text, ts):
        prev = value(self.port, demand(self.head)).decode()
        ref = "msgs/%s-%d" % (self.user, self.seq)
        self.seq += 1
        entry = comp(CONCAT, demand(prev),
                     lit("[%s] %s: %s\n" % (ts, self.user, text)))
        value(self.port, comp(CONCAT,
                              comp(EMIT_DISK, lit(ref), lit(entry)),
                              comp(EMIT_DISK, lit(self.head), lit(lit(ref)))))


def merged(port):
    """The merged thread IS this instruction — stored nowhere."""
    a = value(port, demand("threads/general-alice")).decode()
    b = value(port, demand("threads/general-bob")).decode()
    return comp(SORT, comp(CONCAT, demand(a), demand(b)), NL, lit("text"))


def ts(i):
    return "2026-07-09 15:00:%02d.%03d" % (i, i)


def main():
    for w in (WA, WB):
        shutil.rmtree(w, ignore_errors=True)
        os.makedirs(w)
    ra = start_router(WA, PA)
    rb = start_router(WB, PB)
    try:
        alice = Writer("alice", PA)
        bob = Writer("bob", PB)
        # interleaved posting, each writer on its own node only
        alice.post("first from A", ts(1))
        bob.post("first from B", ts(2))
        alice.post("second from A", ts(3))
        bob.post("second from B", ts(4))

        # exchange chains both ways; each node ships only what its
        # writer owns — replication respects write ownership (see
        # am/sync.py and FRICTION.md #31)
        OWN_A = ["msgs/alice", "threads/general-alice"]
        OWN_B = ["msgs/bob", "threads/general-bob"]
        sync(WA, "127.0.0.1", PB, prefixes=OWN_A)
        sync(WB, "127.0.0.1", PA, prefixes=OWN_B)

        ma = value(PA, merged(PA))
        mb = value(PB, merged(PB))
        assert ma == mb, "nodes did not converge"
        lines = ma.decode().splitlines()
        assert [l.split("] ")[1] for l in lines] == [
            "alice: first from A", "bob: first from B",
            "alice: second from A", "bob: second from B"], lines
        print("convergence: PASS (merged views byte-identical on both nodes, "
              "chronological, no head ever had two writers)")

        # views are queries — composed, stored nowhere
        newest2 = value(PA, comp(LAST, merged(PA), NL, lit("2")))
        assert b"second from A" in newest2 and b"second from B" in newest2
        alice_only = value(PB, comp(SELECT, merged(PB), NL, lit("] alice: ")))
        assert alice_only.count(b"\n") == 2 and b"bob" not in alice_only
        print("derived views: PASS (newest-2 and alice-only composed over "
              "the merge, no storage, no new structures)")

        # divergence is honest, re-sync converges again
        alice.post("post-sync from A", ts(5))
        bob.post("post-sync from B", ts(6))
        da = value(PA, merged(PA))
        db = value(PB, merged(PB))
        assert da != db, "should diverge before re-sync"
        sync(WA, "127.0.0.1", PB, prefixes=OWN_A)
        sync(WB, "127.0.0.1", PA, prefixes=OWN_B)
        ca = value(PA, merged(PA))
        cb = value(PB, merged(PB))
        assert ca == cb and b"post-sync from A" in ca and b"post-sync from B" in ca
        print("divergence + re-sync: PASS (views differ while unsynced — the "
              "world changed across a demand boundary — and reconverge after)")

        results = dict(
            merged_lines=ma.decode().splitlines(),
            converged=True, new_structures=0, new_grammar_nodes=0,
            coordination_machinery="none — one writer per head, merge at fire time",
        )
        with open(os.path.join(ROOT, "phase7-results.json"), "w") as f:
            json.dump(results, f, indent=1)
        print("PASS")
        return 0
    finally:
        ra.send_signal(signal.SIGTERM)
        ra.wait()
        rb.send_signal(signal.SIGTERM)
        rb.wait()


if __name__ == "__main__":
    sys.exit(main())
