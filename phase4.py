"""Phase 4 — computation pressure + shape condensation.

The question: how much does the UNIVERSAL library grow when workloads
demand arithmetic and iteration, and how much computation can be
COMPOSED from existing structures instead? Rules carried from phase 2:
every operation parameter (mode, comparator, threshold, count) is a
VALUE; nothing fold-shaped ever takes a sub-instruction to fire.

Workload: an expense ledger on the message-board world. Amounts-only
chains per user (store shape follows query need — the phase-2 lesson),
budgets as demandable values, the board itself posting normally. Queries:
totals, extremes, average, sorted listing, threshold filter+count, and
remaining-budget (a join-shape composed across chains by the demander).

Then the shape-condensation pass (am/shapemine.py) promotes the recurring
message and ledger composition shapes, the router reloads, and every
query and read must return byte-identical results.

Run from repo root: python3 phase4.py
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(ROOT, "world")
PORT = 7811

sys.path.insert(0, ROOT)
from am.instruction import Incomplete, comp, demand, lit, outcome, skip
from am.structures import (CONCAT, DIV, EMIT_DISK, LAST, PICK, SELECT, SORT,
                           SUB, SUM, TALLY)

NL = lit("\n")


def call(instr):
    with socket.create_connection(("127.0.0.1", PORT)) as s:
        s.sendall(instr)
        buf = b""
        while True:
            try:
                end = skip(buf, 0)
                break
            except Incomplete:
                data = s.recv(65536)
                assert data, "router closed"
                buf += data
    return outcome(buf[:end])


def value(instr):
    kind, v = call(instr)
    assert kind == "value", v
    return v


def start_router():
    p = subprocess.Popen(
        [sys.executable, "-m", "am.router", "--world", WORLD,
         "--port", str(PORT), "--stats", os.devnull],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", PORT), 0.2).close()
            return p
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("router did not come up")


def head(thread):
    return value(demand(thread)).decode()


def new_chain(headref, genesis_ref):
    value(comp(CONCAT,
               comp(EMIT_DISK, lit(genesis_ref), lit(lit(b""))),
               comp(EMIT_DISK, lit(headref), lit(lit(genesis_ref)))))


def append_amount(user, amount, seq):
    headref = "ledgers/" + user
    prev = head(headref)
    ref = "amts/%s-%d" % (user, seq)
    entry = comp(CONCAT, demand(prev), lit(str(amount)), NL)
    value(comp(CONCAT,
               comp(EMIT_DISK, lit(ref), lit(entry)),
               comp(EMIT_DISK, lit(headref), lit(lit(ref)))))


def board_post(thread, user, text):
    r = subprocess.run([sys.executable, "-m", "am.client", "post", thread,
                        user, text], cwd=ROOT, capture_output=True,
                       env={**os.environ, "AM_PORT": str(PORT)})
    assert r.returncode == 0, r.stderr


LEDGERS = {
    "alice": [129, 45, 1200],
    "bob": [300, 300],
    "carol": [50, 75, 25, 850],
}
BUDGETS = {"alice": 2000, "bob": 500, "carol": 900}


def queries():
    """Every query is one composed instruction; returns {name: bytes}."""
    out = {}
    for user in LEDGERS:
        chain = head("ledgers/" + user)
        d = lambda: demand(chain)
        out[user + ".total"] = value(comp(SUM, d(), NL))
        # extremes: composed from sort+last — no max/min structures
        out[user + ".max"] = value(comp(LAST, comp(SORT, d(), NL, lit("num")), NL, lit("1")))
        out[user + ".min"] = value(comp(LAST, comp(SORT, d(), NL, lit("numdesc")), NL, lit("1")))
        # average: composed from div(sum, tally) — no avg structure
        out[user + ".avg"] = value(comp(DIV, comp(SUM, d(), NL),
                                        comp(TALLY, d(), NL, lit(""))))
        # threshold filter and its count: pick, tally∘pick
        out[user + ".over100"] = value(comp(PICK, d(), NL, lit("ge"), lit("100")))
        out[user + ".n_over"] = value(comp(TALLY, comp(PICK, d(), NL, lit("ge"), lit("100")), NL, lit("")))
        out[user + ".sorted"] = value(comp(SORT, d(), NL, lit("num")))
        # join-shape: budget − spent, composed across two chains
        out[user + ".left"] = value(comp(SUB, demand("budgets/" + user),
                                         comp(SUM, d(), NL)))
    # the board still works, and boards and ledgers compose:
    thread = head("threads/general")
    out["board"] = value(demand(thread))
    out["board.alice_posts"] = value(comp(SELECT, demand(thread), NL, lit("] alice: ")))
    return out


def main():
    shutil.rmtree(WORLD, ignore_errors=True)
    router = start_router()
    try:
        # board activity (3 users, shapes recur across >= 3 files)
        subprocess.run([sys.executable, "-m", "am.client", "new-thread",
                        "general"], cwd=ROOT, capture_output=True,
                       env={**os.environ, "AM_PORT": str(PORT)}, check=True)
        board_post("general", "alice", "logging expenses now")
        time.sleep(0.002)
        board_post("general", "bob", "same here")
        time.sleep(0.002)
        board_post("general", "carol", "me three")
        # ledgers + budgets
        for user, amounts in LEDGERS.items():
            new_chain("ledgers/" + user, "amts/%s-genesis" % user)
            for i, amount in enumerate(amounts):
                append_amount(user, amount, i)
            value(comp(EMIT_DISK, lit("budgets/" + user),
                       lit(lit(str(BUDGETS[user])))))
        # empty ledger for the refusal path
        new_chain("ledgers/dave", "amts/dave-genesis")

        before = queries()
        expect = {
            "alice.total": b"1374", "alice.max": b"1200\n", "alice.min": b"45\n",
            "alice.avg": b"458", "alice.over100": b"129\n1200\n",
            "alice.n_over": b"2", "alice.left": b"626",
            "bob.total": b"600", "bob.left": b"-100",
            "carol.total": b"1000", "carol.left": b"-100",
            "carol.max": b"850\n", "carol.n_over": b"1",
        }
        for k, v in expect.items():
            assert before[k] == v, (k, before[k], v)
        # composed-refusal paths: average over empty ledger divides by zero
        dave = head("ledgers/dave")
        assert value(comp(SUM, demand(dave), NL)) == b"0"
        kind, err = call(comp(DIV, comp(SUM, demand(dave), NL),
                              comp(TALLY, demand(dave), NL, lit(""))))
        assert kind == "error" and b"division by zero" in err, (kind, err)
        kind, err = call(comp(SORT, demand(head("threads/general")), NL, lit("num")))
        assert kind == "error" and b"not a number" in err   # text lines refuse numeric sort
        print("queries: PASS (%d results, refusal paths refuse)" % len(before))
    finally:
        router.send_signal(signal.SIGTERM)
        router.wait()

    # shape condensation (offline), then idempotency
    size0 = store_bytes()
    from am.shapemine import run as shapemine
    r1 = shapemine(WORLD, log_path=os.path.join(ROOT, "LIBRARY.md"))
    r2 = shapemine(WORLD)
    assert r2["rewritten"] == 0 and not r2["admitted"], "not idempotent"
    size1 = store_bytes()

    # reload router (promoted shapes now resident), everything byte-identical
    router = start_router()
    try:
        after = queries()
        assert after == before, "shape condensation changed results"
    finally:
        router.send_signal(signal.SIGTERM)
        router.wait()
    print("shape condensation: PASS (%d shapes, %d instances rewritten, "
          "idempotent, all %d results byte-identical after reload)"
          % (len(r1["admitted"]), r1["rewritten"], len(after)))

    results = dict(
        queries={k: v.decode(errors="replace") for k, v in before.items()},
        shapes=r1["admitted"],
        instruction_bytes_before=size0, instruction_bytes_after=size1,
    )
    with open(os.path.join(ROOT, "phase4-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    for a in r1["admitted"]:
        print("  sid=%d %s ×%d slots=%d folded=%dB/inst saved=%dB"
              % (a["sid"], a["sig"], a["instances"], a["holes"],
                 a["folded"], a["saved"]))
    print("stored instruction bytes: %d -> %d" % (size0, size1))
    print("PASS")


def store_bytes():
    total = 0
    for dirpath, _, names in os.walk(WORLD):
        for n in names:
            total += os.lstat(os.path.join(dirpath, n)).st_size
    return total


if __name__ == "__main__":
    main()
