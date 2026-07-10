"""Phase 13 — THE metric: end-to-end cost of the same job, both stacks.

Everything before this compared model pieces against storage primitives
(cat, tar.gz, ext4). Section 0's actual indictment is the application
pipeline: the same information re-encoded and re-materialized many
times between its birth and its use. So: one identical job, two
idiomatic implementations, mechanical accounting.

THE JOB: 5 producers submit 2,000 expense records each (user, amount,
note) to a server over a socket; the server stores them durably; then a
client asks two questions per user (total spent; count of expenses >=
5000) and consumes the answers. Both pipelines must produce identical
answers — asserted.

CONVENTIONAL (the canonical simple service): producer json.dumps each
record -> socket -> server json.loads (validate) -> append the raw JSON
line to a log file -> each query reads the file and json.loads every
line -> aggregate -> json.dumps response -> client json.loads.

MODEL: producer builds one instruction per record (two emits: the
record chain entry and the amounts-projection entry — the phase-8
write-side projection) -> the router fires it -> each query is one
instruction (sum / tally-of-pick over the demanded projection chain) ->
the answer returns as a value, used directly.

THE ACCOUNTING (mechanical, charged identically on both sides):
- crossings_bytes: every byte that passes through a format converter or
  is materialized as an intermediate representation of the data.
  Conventional: json.dumps output + json.loads input, at every site.
  Model: constructed instruction bytes at the producer, PLUS the
  rendered chain value each query materializes inside its firing
  (charged even though it is in-flight — no unfair discount).
- copy_bytes: socket sends/recvs + file writes/reads at the app level.
- wall seconds, per stage. (Caveat printed with the table: the model
  side runs a pure-Python interpreter against C-accelerated json;
  phase 11 measured the native fire loop at 0.86x of cat, so wall time
  is the implementation, crossings are the concept.)

Note on design fairness, stated openly: the conventional side is the
log+scan design. An indexed design would shift query cost to ingest-time
machinery (an index/materialized view) — the machinery class the model
expresses as its write-side projection, which the model side DOES pay
for here, in both crossings and copies.

Run from repo root: python3 phase13.py
"""

import json
import os
import random
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "phase13")
WORLD = os.path.join(WORK, "world")
PORT_CONV, PORT_AM = 7881, 7882
USERS = ["alice", "bob", "carol", "dave", "eve"]
PER_USER = 2000
THRESH = 5000

sys.path.insert(0, ROOT)
from am.instruction import comp, demand, lit, outcome, skip, Incomplete
from am.structures import CONCAT, EMIT_DISK, PICK, SUM, TALLY

NL = lit("\n")
rng = random.Random(13)


def make_records():
    recs = []
    for user in USERS:
        for i in range(PER_USER):
            recs.append(dict(user=user, amount=rng.randrange(1, 10000),
                             note="expense %d for %s in category %d"
                             % (i, user, rng.randrange(20))))
    rng.shuffle(recs)
    return recs


class Counters:
    def __init__(self):
        self.crossings = 0   # bytes through converters / materialized forms
        self.copies = 0      # bytes through sockets and files


# ---------------------------------------------------------------- conventional

class ConvServer(threading.Thread):
    """The canonical JSON-over-socket service with a JSON-lines log."""

    def __init__(self, counters):
        super().__init__(daemon=True)
        self.c = counters
        self.log = os.path.join(WORK, "conv-data.jsonl")
        self.sock = socket.create_server(("127.0.0.1", PORT_CONV))

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn, conn.makefile("rwb") as f:
                for line in f:
                    self.c.copies += len(line)
                    req = json.loads(line)              # crossing: decode
                    self.c.crossings += len(line)
                    if req["op"] == "add":
                        with open(self.log, "ab") as lf:
                            lf.write(line)              # copy: store raw line
                        self.c.copies += len(line)
                        resp = b'{"ok":true}\n'
                    else:
                        totals = {}
                        with open(self.log, "rb") as lf:
                            data = lf.read()
                        self.c.copies += len(data)
                        for rline in data.splitlines():
                            rec = json.loads(rline)     # crossing: decode
                            self.c.crossings += len(rline)
                            if req["op"] == "total":
                                if rec["user"] == req["user"]:
                                    totals[rec["user"]] = \
                                        totals.get(rec["user"], 0) + rec["amount"]
                            else:   # count_ge
                                if rec["user"] == req["user"] \
                                        and rec["amount"] >= req["t"]:
                                    totals[rec["user"]] = \
                                        totals.get(rec["user"], 0) + 1
                        out = json.dumps(dict(value=totals.get(req["user"], 0)))
                        self.c.crossings += len(out)    # crossing: encode
                        resp = out.encode() + b"\n"
                    f.write(resp)
                    f.flush()
                    self.c.copies += len(resp)


def run_conventional(records):
    c = Counters()
    server = ConvServer(c)
    server.start()
    t0 = time.monotonic()
    answers = {}
    with socket.create_connection(("127.0.0.1", PORT_CONV)) as s, \
            s.makefile("rwb") as f:
        for rec in records:
            out = json.dumps(dict(op="add", **rec))     # crossing: encode
            c.crossings += len(out)
            wire = out.encode() + b"\n"
            f.write(wire)
            c.copies += len(wire)
        f.flush()
        # (responses to adds are read in bulk below with the queries)
        for _ in records:
            resp = f.readline()
            c.copies += len(resp)
            json.loads(resp)                            # crossing: decode
            c.crossings += len(resp)
        t_ingest = time.monotonic() - t0
        t0 = time.monotonic()
        for user in USERS:
            for op in ("total", "count_ge"):
                req = json.dumps(dict(op=op, user=user, t=THRESH))
                c.crossings += len(req)                 # crossing: encode
                f.write(req.encode() + b"\n")
                f.flush()
                c.copies += len(req) + 1
                resp = f.readline()
                c.copies += len(resp)
                val = json.loads(resp)["value"]         # crossing: decode
                c.crossings += len(resp)
                answers[(user, op)] = val
        t_query = time.monotonic() - t0
    server.sock.close()
    return answers, c, t_ingest, t_query


# --------------------------------------------------------------------- model

def am_call(f, c, instr):
    f.write(instr)
    f.flush()
    c.copies += len(instr)
    buf = b""
    while True:
        try:
            end = skip(buf, 0)
            break
        except Incomplete:
            data = f.read1(65536)
            assert data
            buf += data
    c.copies += end
    return outcome(buf[:end])


def run_model(records):
    shutil.rmtree(WORLD, ignore_errors=True)
    router = subprocess.Popen(
        [sys.executable, "-m", "am.router", "--world", WORLD,
         "--port", str(PORT_AM), "--stats", os.devnull],
        cwd=ROOT, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", PORT_AM), 0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    c = Counters()
    answers = {}
    try:
        with socket.create_connection(("127.0.0.1", PORT_AM)) as s, \
                s.makefile("rwb") as f:
            t0 = time.monotonic()
            prev_rec = {u: None for u in USERS}
            prev_amt = {u: None for u in USERS}
            seq = {u: 0 for u in USERS}
            # genesis chains per user (empty literals)
            for u in USERS:
                instr = comp(CONCAT,
                             comp(EMIT_DISK, lit("rec/%s-g" % u), lit(lit(b""))),
                             comp(EMIT_DISK, lit("amt/%s-g" % u), lit(lit(b""))))
                c.crossings += len(instr)   # crossing: construction
                copy_files = len(lit(b"")) * 2
                c.copies += copy_files
                am_call(f, c, instr)
                prev_rec[u], prev_amt[u] = "rec/%s-g" % u, "amt/%s-g" % u
            for rec in records:
                u = rec["user"]
                n = seq[u]
                seq[u] += 1
                rref, aref = "rec/%s-%d" % (u, n), "amt/%s-%d" % (u, n)
                recfile = comp(CONCAT, demand(prev_rec[u]),
                               lit("%s %d %s\n" % (u, rec["amount"], rec["note"])))
                amtfile = comp(CONCAT, demand(prev_amt[u]),
                               lit("%d\n" % rec["amount"]))
                instr = comp(CONCAT,
                             comp(EMIT_DISK, lit(rref), lit(recfile)),
                             comp(EMIT_DISK, lit(aref), lit(amtfile)))
                c.crossings += len(instr)   # crossing: construction (once)
                c.copies += len(recfile) + len(amtfile)   # file writes
                kind, _ = am_call(f, c, instr)
                assert kind == "value"
                prev_rec[u], prev_amt[u] = rref, aref
            t_ingest = time.monotonic() - t0
            t0 = time.monotonic()
            for u in USERS:
                chain = prev_amt[u]
                # the query fires the projection chain: charge the rendered
                # intermediate it materializes, plus the file reads
                rendered = sum(len(b"%d\n" % r["amount"]) for r in records
                               if r["user"] == u)
                for op, instr in (
                        ("total", comp(SUM, demand(chain), NL)),
                        ("count_ge", comp(TALLY,
                                          comp(PICK, demand(chain), NL,
                                               lit("ge"), lit(str(THRESH))),
                                          NL, lit("")))):
                    c.crossings += len(instr) + rendered   # construction + render
                    c.copies += rendered                    # chain file reads
                    kind, val = am_call(f, c, instr)
                    assert kind == "value"
                    answers[(u, op)] = int(val)             # consumed directly
            t_query = time.monotonic() - t0
    finally:
        router.send_signal(signal.SIGTERM)
        router.wait()
    return answers, c, t_ingest, t_query


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    records = make_records()
    payload = sum(len(json.dumps(r)) for r in records)

    conv_ans, cc, conv_ti, conv_tq = run_conventional(records)
    am_ans, mc, am_ti, am_tq = run_model(records)
    assert conv_ans == am_ans, "pipelines disagree on the answers"

    def row(name, conv, model, fmt="%.2f"):
        print("  %-34s %14s %14s" % (name, fmt % conv, fmt % model))

    print("\nTHE METRIC — same job, both stacks (%d records, %.2f MB payload,"
          " %d queries, identical answers)\n"
          % (len(records), payload / 1e6, 2 * len(USERS)))
    print("  %-34s %14s %14s" % ("", "conventional", "model"))
    row("crossings bytes / payload byte", cc.crossings / payload,
        mc.crossings / payload)
    row("copy bytes / payload byte", cc.copies / payload, mc.copies / payload)
    row("ingest wall s", conv_ti, am_ti)
    row("query wall s", conv_tq, am_tq)
    print("\n  (wall-time caveat: pure-Python fire loop vs C-accelerated json;"
          "\n   phase 11 measured native firing at 0.86x of cat)")
    results = dict(
        records=len(records), payload_bytes=payload,
        conventional=dict(crossings=cc.crossings, copies=cc.copies,
                          ingest_s=round(conv_ti, 2), query_s=round(conv_tq, 2)),
        model=dict(crossings=mc.crossings, copies=mc.copies,
                   ingest_s=round(am_ti, 2), query_s=round(am_tq, 2)),
        crossings_ratio=round(cc.crossings / mc.crossings, 2),
    )
    with open(os.path.join(ROOT, "phase13-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("\ncrossings ratio (conventional / model): %.2fx" %
          results["crossings_ratio"])
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
