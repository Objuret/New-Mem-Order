"""Phase 15 — the compute half: can the model run a PROGRAM?

Everything so far computed aggregates. A program needs more: branching
on data, decisions that depend on previous decisions, a multi-step
workflow. The rule "nothing fires values" bans conditionals that choose
which code runs — so can conditional logic exist here at all?

THE WORKLOAD: an account with deposits and a stream of 200 orders. The
rule: approve an order iff its amount fits in the balance LEFT BY EVERY
PREVIOUS DECISION; otherwise decline. Sequential dependence, two
branches, real state over time.

HOW BRANCHING COMPOSES (zero new structures — the phase's bet):

  balance   = sub(sum(demand(deposits)), sum(demand(approved)))
  fits(a)   = tally(pick(lit("a\\n"), "\\n", "le", balance), "\\n", "")   -> "1"/"0"
  decision  = select(lit("1 approve\\n0 decline\\n"), "\\n",
                     concat(fits(a), lit(" ")))                     -> the branch

The condition is computed as a VALUE and selects between alternatives
that exist as DATA. Both alternatives are just bytes; nothing is ever
fired conditionally. This is branching the way SQL CASE and SIMD
select branch — eager, data-shaped, effect-free.

WHAT THE MODEL CANNOT DO (measured by construction, logged in
FRICTION): choose which EFFECT fires (the world receives the decision
value and emits the corresponding event — the pump), skip computing the
untaken branch, or loop unboundedly (the world pumps; each stroke is
one firing). Control flow lives in the world; decisions live in the
model.

GATES: a plain-Python reference implementation must agree on all 200
decisions and the final balance; both branches must actually occur; and
the processor is killed and rebuilt from the world mid-run — its memory
of heads is recovered by demanding, and decisions must be unaffected.

Run from repo root: python3 phase15.py
"""

import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(ROOT, "world15")
PORT = 7971

sys.path.insert(0, ROOT)
from am.instruction import comp, demand, lit
from am.structures import CONCAT, EMIT_DISK, PICK, SELECT, SUB, SUM, TALLY
from am.sync import call

NL = lit("\n")
rng = random.Random(15)


def value(instr):
    kind, v = call("127.0.0.1", PORT, instr)
    assert kind == "value", v
    return v


class Processor:
    """The world-side pump: fires the rule, materializes the outcome.
    Holds only references — killed and rebuilt mid-run to prove it."""

    def __init__(self):
        # recover heads from the world (restart = demand, no recovery code)
        def head(ref, genesis):
            kind, v = call("127.0.0.1", PORT, demand(ref))
            if kind == "error":
                value(comp(CONCAT,
                           comp(EMIT_DISK, lit(genesis), lit(lit(b""))),
                           comp(EMIT_DISK, lit(ref), lit(lit(genesis)))))
                return genesis
            return v.decode()
        self.dep = head("heads/deposits", "dep/genesis")
        self.appr = head("heads/approved", "appr/genesis")
        self.ev = head("heads/events", "ev/genesis")
        self.seq = int(value(comp(TALLY, demand(self.ev), NL, lit(""))))

    def _swap(self, entries):
        """entries: list of (chain_attr, new_ref, appended_line). One
        indivisible firing: chain entries + head swaps."""
        emits = []
        for attr, ref, line in entries:
            prev = getattr(self, attr)
            emits.append(comp(EMIT_DISK, lit(ref),
                              lit(comp(CONCAT, demand(prev), lit(line)))))
            emits.append(comp(EMIT_DISK,
                              lit("heads/" + {"dep": "deposits",
                                              "appr": "approved",
                                              "ev": "events"}[attr]),
                              lit(lit(ref))))
        value(comp(CONCAT, *emits))
        for attr, ref, _ in entries:
            setattr(self, attr, ref)

    def deposit(self, amount):
        n = self.seq
        self.seq += 1
        self._swap([("dep", "dep/%d" % n, "%d\n" % amount),
                    ("ev", "ev/%d" % n, "deposit %d\n" % amount)])

    def order(self, amount):
        n = self.seq
        self.seq += 1
        balance = comp(SUB, comp(SUM, demand(self.dep), NL),
                       comp(SUM, demand(self.appr), NL))
        fits = comp(TALLY,
                    comp(PICK, lit("%d\n" % amount), NL, lit("le"), balance),
                    NL, lit(""))
        decision = value(comp(SELECT, lit("1 approve\n0 decline\n"), NL,
                              comp(CONCAT, fits, lit(" "))))
        # the pump: the world maps the decided VALUE to the effects
        if decision == b"1 approve\n":
            self._swap([("appr", "appr/%d" % n, "%d\n" % amount),
                        ("ev", "ev/%d" % n, "approve %d\n" % amount)])
            return True
        assert decision == b"0 decline\n", decision
        self._swap([("ev", "ev/%d" % n, "decline %d\n" % amount)])
        return False


def main():
    shutil.rmtree(WORLD, ignore_errors=True)
    router = subprocess.Popen(
        [sys.executable, "-m", "am.router", "--world", WORLD,
         "--port", str(PORT), "--stats", os.devnull],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    import socket
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", PORT), 0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    try:
        ops = []
        for i in range(200):
            if i % 25 == 0:
                ops.append(("deposit", rng.randrange(3000, 9000)))
            ops.append(("order", rng.randrange(100, 4000)))

        # reference implementation: plain Python, same rule
        ref_balance = 0
        ref_decisions = []
        for kind, amount in ops:
            if kind == "deposit":
                ref_balance += amount
                ref_decisions.append("deposit")
            elif amount <= ref_balance:
                ref_balance -= amount
                ref_decisions.append("approve")
            else:
                ref_decisions.append("decline")

        proc = Processor()
        model_decisions = []
        for i, (kind, amount) in enumerate(ops):
            if i == len(ops) // 2:
                proc = Processor()   # kill the pump mid-run; rebuild from world
            if kind == "deposit":
                proc.deposit(amount)
                model_decisions.append("deposit")
            else:
                model_decisions.append(
                    "approve" if proc.order(amount) else "decline")

        assert model_decisions == ref_decisions, "decisions diverge from reference"
        n_app = model_decisions.count("approve")
        n_dec = model_decisions.count("decline")
        assert n_app and n_dec, "both branches must occur"

        final_balance = int(value(
            comp(SUB, comp(SUM, demand(proc.dep), NL),
                 comp(SUM, demand(proc.appr), NL))))
        assert final_balance == ref_balance, (final_balance, ref_balance)

        # the audit trail is a query over the events chain
        declines = value(comp(TALLY, demand(proc.ev), NL, lit("decline")))
        assert int(declines) == n_dec

        print("program: PASS — %d sequential decisions (%d approve, "
              "%d decline), every one identical to the reference "
              "implementation; final balance %d verified; processor killed "
              "and rebuilt from the world mid-run with no effect"
              % (len(ops), n_app, n_dec, final_balance))
        print("branching: composed from the existing library "
              "(select ∘ concat(tally ∘ pick, ' ') over data alternatives) — "
              "ZERO new structures, zero grammar changes")
        results = dict(operations=len(ops), approved=n_app, declined=n_dec,
                       final_balance=final_balance,
                       new_structures=0, new_grammar_nodes=0)
        with open(os.path.join(ROOT, "phase15-results.json"), "w") as f:
            json.dump(results, f, indent=1)
        print("PASS")
        return 0
    finally:
        router.send_signal(signal.SIGTERM)
        router.wait()


if __name__ == "__main__":
    sys.exit(main())
