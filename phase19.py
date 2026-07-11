"""Phase 19 — the sharp test: computation-shaped work + fused-vs-parts.

Jocke's charter (2026-07-11, after the external review): "put genuinely
computation-shaped work (not storage-shaped) on it and watch whether
the universal tier stays small — and find any regime where the fused
design beats building the same capabilities out of off-the-shelf
parts."

PART A — ten diverse computation tasks (aggregation, order statistics,
text analytics, bucketing, transformation, weighted reduction) run as
instructions over one ingested dataset, every answer asserted equal to
a plain-Python reference. Compose-first discipline: a structure is
added only when composition provably cannot reach the answer. The
growth curve IS the result, and the falsification condition is CODED
(review #3's lesson): if additions grow linearly with tasks
(> 1 per 2 tasks), print FALSIFICATION SIGNAL and exit nonzero.

PART B — the same two-node, sync-heavy job on two stacks, end to end
over real sockets on both sides:
  fused: two amd routers (C), chains + write-side projections,
         am/sync.py replication, queries as instructions;
  parts: two sqlite3 databases (C, indexed) behind tiny TCP servers,
         idiomatic app-level row replication, SQL queries.
Both stacks pay the wire for ingest, replication, and queries; answers
asserted identical every round. Two regimes probe where boundary-
crossing frequency dominates vs where bulk work dominates:
  chatty: 40 rounds x 10 records/round
  bulky:   4 rounds x 400 records/round
Walls are min..max of 3 repeats (review: no single-run findings).
"No regime found where fused wins" is an admissible, reportable
verdict — that is what makes this a test.

Run from repo root: python3 phase19.py    (~3-6 minutes)
"""

import json
import os
import random
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "phase19")
AMD = os.path.join(ROOT, "native", "amd")
PORTS = iter(range(8020, 8090))

sys.path.insert(0, ROOT)
from am.instruction import Incomplete, comp, demand, lit, outcome, skip
from am.structures import (CONCAT, DIV, EMIT_DISK, LAST, PICK, REPLACE,
                           SCALE, SELECT, SORT, SUB, SUM, TALLY, UNIQ)
from am.sync import call, sync

NL = lit("\n")
SP = lit(" ")
rng = random.Random(19)

VOCAB = ("travel food rent tools books fuel coffee gear repairs tax "
         "gift cinema hotel trains phone cloud paper seeds paint rope").split()
USERS_A = ["alice", "ann"]
USERS_B = ["bob", "ben"]


def wait_port(port, proc=None):
    for _ in range(200):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return
        except OSError:
            if proc and proc.poll() is not None:
                raise RuntimeError("server died")
            time.sleep(0.03)
    raise RuntimeError("port never opened")


# ============================ PART A =====================================

def make_records_a(n=3000):
    recs = []
    users = USERS_A + USERS_B
    for i in range(n):
        recs.append(dict(
            user=users[rng.randrange(4)],
            amount=rng.randrange(1, 10000),
            qty=rng.randrange(1, 9),
            note=" ".join(rng.choice(VOCAB)
                          for _ in range(rng.randrange(3, 8)))))
    return recs


class Router:
    """The Python router (it holds the full universal tier) on a socket."""

    def __init__(self, world):
        self.world = world
        self.port = next(PORTS)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "am.router", "--world", world,
             "--port", str(self.port), "--stats", os.devnull],
            cwd=ROOT, stderr=subprocess.DEVNULL)
        wait_port(self.port, self.proc)
        self.sock = socket.create_connection(("127.0.0.1", self.port))
        self.f = self.sock.makefile("rwb")

    def fire(self, instr):
        self.f.write(instr)
        self.f.flush()
        buf = b""
        while True:
            try:
                end = skip(buf, 0)
                break
            except Incomplete:
                data = self.f.read1(65536)
                assert data, "router closed"
                buf += data
        kind, val = outcome(buf[:end])
        assert kind == "value", val
        return val

    def stop(self):
        self.proc.send_signal(signal.SIGTERM)
        self.proc.wait()


def ingest_a(r, records):
    """Chains per user: amt (amounts), note (words), prod (the model
    computes amount*qty at render time via scale — a write-side
    projection whose values the MODEL computes, not the writer)."""
    users = USERS_A + USERS_B
    prev = {}
    for u in users:
        for c in ("amt", "note", "prod"):
            ref = "%s/%s-g" % (c, u)
            r.fire(comp(EMIT_DISK, lit(ref), lit(lit(b""))))
            prev[(c, u)] = ref
    seq = {u: 0 for u in users}
    for rec in records:
        u = rec["user"]
        n = seq[u]
        seq[u] += 1
        link = {
            "amt": comp(CONCAT, demand(prev[("amt", u)]),
                        lit(b"%d\n" % rec["amount"])),
            "note": comp(CONCAT, demand(prev[("note", u)]),
                         lit(rec["note"].encode() + b"\n")),
            "prod": comp(CONCAT, demand(prev[("prod", u)]),
                         comp(SCALE, lit(b"%d\n" % rec["amount"]), NL,
                              lit(b"%d" % rec["qty"]))),
        }
        for c, instr in link.items():
            ref = "%s/%s-%d" % (c, u, n)
            r.fire(comp(EMIT_DISK, lit(ref), lit(instr)))
            prev[(c, u)] = ref
    return prev


def all_chain(prev, kind):
    return comp(CONCAT, *[demand(prev[(kind, u)])
                          for u in USERS_A + USERS_B])


def element_at(chain_instr, n, i):
    """Ascending element i, composed: suffix from i (last n-i of the
    ascending sort) then its minimum (last 1 of that suffix re-sorted
    descending). No 'first' structure exists; this is the honest cost."""
    return comp(LAST,
                comp(SORT,
                     comp(LAST, comp(SORT, chain_instr, NL, lit("num")),
                          NL, lit(str(n - i))),
                     NL, lit("numdesc")),
                NL, lit("1"))


def part_a():
    print("PART A — computation battery (10 tasks, compose-first)\n")
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    records = make_records_a()
    r = Router(os.path.join(WORK, "worldA"))
    additions = []   # (structure/extension, forced-by-task)
    try:
        t0 = time.monotonic()
        prev = ingest_a(r, records)
        t_ingest = time.monotonic() - t0
        users = USERS_A + USERS_B
        by_user = {u: [x for x in records if x["user"] == u] for u in users}
        amounts = [x["amount"] for x in records]
        ok = []

        # 1. total per user — composes from phase-2 tier
        for u in users:
            got = int(r.fire(comp(SUM, demand(prev[("amt", u)]), NL)))
            assert got == sum(x["amount"] for x in by_user[u])
        ok.append("1 per-user totals          sum                 composed")

        # 2. global mean (floor) — composes
        got = int(r.fire(comp(DIV,
                              comp(SUM, all_chain(prev, "amt"), NL),
                              comp(TALLY, all_chain(prev, "amt"), NL,
                                   lit("")))))
        assert got == sum(amounts) // len(amounts), got
        ok.append("2 global mean              div(sum,tally)      composed")

        # 3+4. median and p90 — compose via double-sort suffix trick;
        # the count arrives from a prior firing (two-step, the phase-1
        # head pattern: the demander holds a value it was handed)
        n = int(r.fire(comp(TALLY, all_chain(prev, "amt"), NL, lit(""))))
        for name, idx in (("median", (n - 1) // 2),
                          ("p90", (9 * (n - 1)) // 10)):
            got = int(r.fire(element_at(all_chain(prev, "amt"), n, idx)))
            assert got == sorted(amounts)[idx], (name, got)
        ok.append("3 median                   sort/last x2        composed"
                  " (two-step: n first)")
        ok.append("4 p90                      sort/last x2        composed")

        # 5. range = max - min — composes; last() returns a terminated
        # segment ("9999\n") which sub refuses, and sum over the single
        # segment is the tier's own scalar-extraction bridge (friction
        # #12's terminator convention, met compositionally)
        def scalar(seg_expr):
            return comp(SUM, seg_expr, NL)
        got = int(r.fire(comp(SUB,
                              scalar(comp(LAST,
                                          comp(SORT, all_chain(prev, "amt"),
                                               NL, lit("num")), NL,
                                          lit("1"))),
                              scalar(comp(LAST,
                                          comp(SORT, all_chain(prev, "amt"),
                                               NL, lit("numdesc")), NL,
                                          lit("1"))))))
        assert got == max(amounts) - min(amounts)
        ok.append("5 range (max-min)          sub/sort/last       composed")

        # 6. count >= 5000 per user — composes (phase-13 shape)
        for u in users:
            got = int(r.fire(comp(TALLY,
                                  comp(PICK, demand(prev[("amt", u)]), NL,
                                       lit("ge"), lit("5000")),
                                  NL, lit(""))))
            assert got == sum(1 for x in by_user[u] if x["amount"] >= 5000)
        ok.append("6 count>=T per user        tally.pick          composed")

        # 7. top-3 words — FORCED two library changes and one strain:
        #    replace (new structure 12): notes mix "\n" and " "; segment
        #      ops see one delimiter, so the text needs one regime;
        #    pick seq (op-vocabulary extension): word counting needs
        #      whole-segment equality — select/tally are contains-based
        #      (friction #9), and "the" must not match "theatre";
        #    ranking strain: pairing count with word for sort has no
        #      pad/substring, so the pair is ENCODED as count*1000+idx
        #      (scale+sum), sorted numerically, decoded by the demander
        #      from the three returned values (a value it holds).
        words_all = comp(REPLACE, all_chain(prev, "note"), NL, SP)
        wordlist = r.fire(comp(UNIQ, comp(SORT, words_all, SP, lit("text")),
                               SP)).decode().split()
        parts = []
        for i, w in enumerate(wordlist):
            count = comp(TALLY, comp(PICK, words_all, SP, lit("seq"),
                                     lit(w)), SP, lit(""))
            enc = comp(SUM, comp(CONCAT, comp(SCALE, count, NL, lit("1000")),
                                 lit(str(i)), NL), NL)
            parts.extend([enc, NL])
        got = r.fire(comp(LAST, comp(SORT, comp(CONCAT, *parts), NL,
                                     lit("num")), NL, lit("3")))
        top3 = sorted((int(v) // 1000, wordlist[int(v) % 1000])
                      for v in got.split())
        from collections import Counter
        freq = Counter(w for x in records for w in x["note"].split())
        want = sorted((c, w) for w, c in freq.items())[-3:]
        assert top3 == want, (top3, want)
        additions.append(("replace (sid 12)", "task 7"))
        additions.append(("pick op 'seq'/'sne' (vocab ext.)", "task 7"))
        ok.append("7 top-3 words              replace+seq+encode  FORCED"
                  " replace + pick.seq")

        # 8. histogram, 4 buckets — composes (nested pick)
        hist = []
        for lo, hi in ((0, 2500), (2500, 5000), (5000, 7500), (7500, 10000)):
            hist.append(int(r.fire(comp(TALLY,
                                        comp(PICK,
                                             comp(PICK, all_chain(prev, "amt"),
                                                  NL, lit("ge"), lit(str(lo))),
                                             NL, lit("lt"), lit(str(hi))),
                                        NL, lit("")))))
        assert hist == [sum(1 for a in amounts if lo <= a < hi)
                        for lo, hi in ((0, 2500), (2500, 5000),
                                       (5000, 7500), (7500, 10000))]
        ok.append("8 histogram (4 buckets)    tally.pick.pick     composed")

        # 9. all amounts x7, rendered — FORCED scale (sid 13): per-
        #    element arithmetic has no composition; a generic per-element
        #    apply would be eval (forbidden), so the verb enters as ONE
        #    fixed pure structure. THE standing risk, stated: every new
        #    per-element verb costs one structure — this axis is linear.
        got = r.fire(comp(SCALE, all_chain(prev, "amt"), NL, lit("7")))
        want_bytes = b"".join(b"%d\n" % (x["amount"] * 7)
                              for u in users for x in by_user[u])
        assert got == want_bytes
        additions.append(("scale (sid 13)", "task 9"))
        ok.append("9 amounts x7 rendered      scale               FORCED"
                  " scale")

        # 10. weighted total sum(amount*qty) — composes GIVEN scale:
        #     the product chain's links hold scale compositions the model
        #     fires at render time (write-side projection of a zip-shape)
        got = int(r.fire(comp(SUM, all_chain(prev, "prod"), NL)))
        assert got == sum(x["amount"] * x["qty"] for x in records)
        ok.append("10 weighted total          sum.prod-chain      composed"
                  " (write-side zip)")

        for line in ok:
            print("  " + line)
        print("\n  ingest: %d records, %.1fs (Python router; 3 chains/user)"
              % (len(records), t_ingest))
    finally:
        r.stop()

    n_new = sum(1 for a in additions if "vocab" not in a[0])
    n_ext = sum(1 for a in additions if "vocab" in a[0])
    print("\n  GROWTH: universal tier 11 -> %d (+%d structures, +%d op-"
          "vocabulary extension) for 10 computation tasks" %
          (11 + n_new, n_new, n_ext))
    # the CODED falsification condition, pre-stated in the docstring
    if n_new * 2 > 10:
        print("  FALSIFICATION SIGNAL: additions grew linearly with tasks")
        return None
    print("  sub-linear: PASS (standing risk recorded: per-element verbs"
          " are a linear axis — scale is verb #1)")
    return dict(tasks=10, new_structures=n_new, extensions=n_ext,
                additions=["%s <- %s" % a for a in additions],
                ingest_s=round(t_ingest, 2))


# ============================ PART B =====================================

def make_round_records(k, users):
    return [dict(user=users[rng.randrange(len(users))],
                 amount=rng.randrange(1, 10000),
                 note=rng.choice(VOCAB)) for _ in range(k)]


class AmNode:
    """One amd router + this driver's chain bookkeeping (the writer holds
    its own heads, phase-7 ownership; head FILES let the peer discover)."""

    def __init__(self, world, own_users, thresh):
        self.world = world
        self.port = next(PORTS)
        self.proc = subprocess.Popen([AMD, world, str(self.port)],
                                     stderr=subprocess.DEVNULL)
        wait_port(self.port, self.proc)
        self.own = own_users
        self.thresh = thresh
        self.prev = {}
        # writer-held running registers (demander memory of its own
        # outputs, DECISIONS 1.15 precedent) + genesis register files:
        # the model's write-side projection is its index (phase 8/13)
        self.reg = {u: dict(sum=0, cnt=0, note="") for u in own_users}
        for u in own_users:
            for c in ("amt", "note"):
                ref = "%s/%s-g" % (c, u)
                self._fire(comp(EMIT_DISK, lit(ref), lit(lit(b""))))
                self._set_head(c, u, ref)
            self._fire(comp(CONCAT, *self._register_emits(u)))

    def _register_emits(self, u):
        r = self.reg[u]
        return [comp(EMIT_DISK, lit("reg/%s-%s" % (name, u)), lit(lit(val)))
                for name, val in (("sum", b"%d" % r["sum"]),
                                  ("cnt", b"%d" % r["cnt"]),
                                  ("note", r["note"].encode()))]

    def _fire(self, instr):
        kind, val = call("127.0.0.1", self.port, instr)
        assert kind == "value", val
        return val

    def _set_head(self, c, u, ref):
        self.prev[(c, u)] = ref
        self._fire(comp(EMIT_DISK, lit("heads/%s-%s" % (c, u)),
                        lit(lit(ref.encode()))))

    def add(self, recs):
        # the model's own idiom, both axes: a round of appends is ONE
        # firing, and a chain link is one ARRIVAL — this round's whole
        # batch per (chain, user) is a single link holding K lines
        # (spec: instruction per arrival; the board linked per message
        # because messages arrived one at a time). Heads emitted last.
        by_u = {}
        for rec in recs:
            by_u.setdefault(rec["user"], []).append(rec)
        emits = []
        stamp = "%d" % time.monotonic_ns()
        for u, rs in sorted(by_u.items()):
            for c, payload in (
                    ("amt", b"".join(b"%d\n" % x["amount"] for x in rs)),
                    ("note", b"".join(x["note"].encode() + b"\n"
                                      for x in rs))):
                ref = "%s/%s-%s" % (c, u, stamp)
                emits.append(comp(EMIT_DISK, lit(ref), lit(
                    comp(CONCAT, demand(self.prev[(c, u)]), lit(payload)))))
                self.prev[(c, u)] = ref
                emits.append(comp(EMIT_DISK, lit("heads/%s-%s" % (c, u)),
                                  lit(lit(ref.encode()))))
        if emits:
            self._fire(comp(CONCAT, *emits))
        # register maintenance: the MODEL computes the new running
        # values (sum / count>=T over old-register + this round's
        # deltas), the writer holds the outputs and publishes them as
        # register files the peer demands in O(1)
        upd = []
        for u, rs in sorted(by_u.items()):
            delta = b"".join(b"%d\n" % x["amount"] for x in rs)
            upd.append((u, "sum", comp(SUM, comp(
                CONCAT, lit(b"%d\n" % self.reg[u]["sum"]), lit(delta)),
                NL)))
            upd.append((u, "cnt", comp(SUM, comp(
                CONCAT, lit(b"%d\n" % self.reg[u]["cnt"]),
                comp(TALLY, comp(PICK, lit(delta), NL, lit("ge"),
                                 lit(str(self.thresh))), NL, lit("")),
                NL), NL)))
        vals = self.pipelined([i for _, _, i in upd]) if upd else []
        for (u, name, _), v in zip(upd, vals):
            self.reg[u][name] = int(v)
        for u, rs in by_u.items():
            self.reg[u]["note"] = rs[-1]["note"]
        regs = [e for u in sorted(by_u) for e in self._register_emits(u)]
        if regs:
            self._fire(comp(CONCAT, *regs))

    def chain_ref(self, c, u):
        if u in self.own:
            return self.prev[(c, u)]
        return self._fire(demand("heads/%s-%s" % (c, u))).decode()

    def pipelined(self, instrs):
        with socket.create_connection(("127.0.0.1", self.port)) as sk:
            sk.sendall(b"".join(instrs))
            buf, out = b"", []
            while len(out) < len(instrs):
                try:
                    end = skip(buf, 0)
                    kind, val = outcome(buf[:end])
                    assert kind == "value", val
                    out.append(val)
                    buf = buf[end:]
                    continue
                except Incomplete:
                    pass
                data = sk.recv(1 << 20)
                assert data, "amd closed"
                buf += data
            return out

    def queries(self, users, thresh):
        # registers make every query one O(1) demand, own or foreign
        qs = []
        for u in users:
            for name in ("sum", "cnt", "note"):
                qs.append(demand("reg/%s-%s" % (name, u)))
        vals = self.pipelined(qs)
        out = []
        for j in range(0, len(vals), 3):
            out.extend([int(vals[j]), int(vals[j + 1]),
                        vals[j + 2].decode().strip()])
        return out

    def stop(self):
        self.proc.send_signal(signal.SIGTERM)
        self.proc.wait()


class SqlNode(threading.Thread):
    """sqlite3 behind a TCP line protocol: both stacks pay the wire for
    ingest, replication, and queries. Idiomatic and indexed."""

    def __init__(self, path):
        super().__init__(daemon=True)
        self.path = path
        self.port = next(PORTS)
        self.srv = socket.create_server(("127.0.0.1", self.port))
        self.wire = 0
        self.start()

    def run(self):
        db = sqlite3.connect(self.path)
        # guarantee-class parity with the fused side, which never
        # fsyncs (REPORT ERRATA #6): don't bill sqlite for durability
        # the model doesn't provide
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA journal_mode=MEMORY")
        db.execute("CREATE TABLE r (id INTEGER PRIMARY KEY, src TEXT,"
                   " sid INTEGER, user TEXT, amount INTEGER, note TEXT)")
        db.execute("CREATE INDEX iu ON r(user)")
        db.execute("CREATE UNIQUE INDEX isrc ON r(src, sid)")
        db.commit()
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            with conn, conn.makefile("rwb") as f:
                for line in f:
                    self.wire += len(line)
                    req = json.loads(line)
                    if req["op"] == "add":
                        db.executemany(
                            "INSERT INTO r (src,sid,user,amount,note)"
                            " VALUES (?,?,?,?,?)",
                            [(r["src"], r["sid"], r["user"], r["amount"],
                              r["note"]) for r in req["rows"]])
                        db.commit()
                        resp = b'{"ok":1}\n'
                    elif req["op"] == "since":
                        rows = db.execute(
                            "SELECT src,sid,user,amount,note FROM r WHERE"
                            " src=? AND sid>?",
                            (req["src"], req["sid"])).fetchall()
                        resp = (json.dumps([dict(src=a, sid=b, user=c,
                                                 amount=d, note=e)
                                            for a, b, c, d, e in rows])
                                + "\n").encode()
                    else:   # query
                        u, t = req["user"], req["t"]
                        s = db.execute("SELECT COALESCE(SUM(amount),0) FROM"
                                       " r WHERE user=?", (u,)).fetchone()[0]
                        c = db.execute("SELECT COUNT(*) FROM r WHERE user=?"
                                       " AND amount>=?", (u, t)).fetchone()[0]
                        nrow = db.execute(
                            "SELECT note FROM r WHERE user=? ORDER BY id"
                            " DESC LIMIT 1", (u,)).fetchone()
                        resp = (json.dumps([s, c, nrow[0] if nrow else ""])
                                + "\n").encode()
                    f.write(resp)
                    f.flush()
                    self.wire += len(resp)


def sql_rpc(port, obj):
    with socket.create_connection(("127.0.0.1", port)) as s, \
            s.makefile("rwb") as f:
        f.write((json.dumps(obj) + "\n").encode())
        f.flush()
        return json.loads(f.readline())


def ship(src_world, port, since_ns, prefixes):
    """sync.py's discovery and emit-carried moves, pipelined over one
    connection (the wire idiom both stacks get). Same instructions, same
    opacity — an engineering variant of the chartered pass."""
    src = os.path.realpath(src_world)
    instrs = []
    for dirpath, _, names in sorted(os.walk(src)):
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            ref = os.path.relpath(path, src)
            if ref.split(os.sep)[0] == "lib":
                continue
            if not any(ref.startswith(p) for p in prefixes):
                continue
            if os.lstat(path).st_mtime_ns <= since_ns:
                continue
            with open(path, "rb") as f:
                instrs.append(comp(EMIT_DISK, lit(ref), lit(f.read())))
    if not instrs:
        return 0
    with socket.create_connection(("127.0.0.1", port)) as sk:
        sk.sendall(b"".join(instrs))
        buf, got = b"", 0
        while got < len(instrs):
            try:
                end = skip(buf, 0)
                kind, val = outcome(buf[:end])
                assert kind == "value", val
                buf = buf[end:]
                got += 1
                continue
            except Incomplete:
                pass
            data = sk.recv(1 << 20)
            assert data, "amd closed during ship"
            buf += data
    return sum(len(i) for i in instrs)


def run_fused(rounds, k, thresh):
    wa = os.path.join(WORK, "b-am-a")
    wb = os.path.join(WORK, "b-am-b")
    for w in (wa, wb):
        shutil.rmtree(w, ignore_errors=True)
    na, nb = AmNode(wa, USERS_A, thresh), AmNode(wb, USERS_B, thresh)
    answers, wire = [], 0
    try:
        t0 = time.monotonic()
        hwm_a = hwm_b = 0
        pa = ["amt/a", "note/a", "heads/amt-a", "heads/note-a",
              "reg/sum-a", "reg/cnt-a", "reg/note-a"]
        pb = ["amt/b", "note/b", "heads/amt-b", "heads/note-b",
              "reg/sum-b", "reg/cnt-b", "reg/note-b"]
        for _ in range(rounds):
            since = time.time_ns() - 1
            na.add(make_round_records(k, USERS_A))
            wire += ship(wa, nb.port, hwm_a, pa)
            hwm_a = since
            answers.append(nb.queries(USERS_A + USERS_B, thresh))
            since = time.time_ns() - 1
            nb.add(make_round_records(k, USERS_B))
            wire += ship(wb, na.port, hwm_b, pb)
            hwm_b = since
            answers.append(na.queries(USERS_A + USERS_B, thresh))
        wall = time.monotonic() - t0
    finally:
        na.stop()
        nb.stop()
    return answers, wall, wire


def run_parts(rounds, k, thresh):
    pa = os.path.join(WORK, "b-sql-a.db")
    pb = os.path.join(WORK, "b-sql-b.db")
    for p in (pa, pb):
        if os.path.exists(p):
            os.remove(p)
    na, nb = SqlNode(pa), SqlNode(pb)
    time.sleep(0.2)
    answers = []
    sid = {"a": 0, "b": 0}
    hwm = {"a": 0, "b": 0}   # replication high-water mark per source

    repl_wire = [0]

    def add_and_sync(src, dst_port, src_port, recs, key):
        rows = []
        for r in recs:
            sid[key] += 1
            rows.append(dict(src=key, sid=sid[key], **r))
        sql_rpc(src_port, dict(op="add", rows=rows))
        new = sql_rpc(src_port, dict(op="since", src=key, sid=hwm[key]))
        payload = dict(op="add", rows=new)
        repl_wire[0] += len(json.dumps(payload)) + 1
        sql_rpc(dst_port, payload)
        hwm[key] = sid[key]

    def queries(port):
        out = []
        with socket.create_connection(("127.0.0.1", port)) as sk, \
                sk.makefile("rwb") as f:
            for u in USERS_A + USERS_B:
                f.write((json.dumps(dict(op="q", user=u, t=thresh))
                         + "\n").encode())
                f.flush()
                s, c, note = json.loads(f.readline())
                out.extend([s, c, note])
        return out

    t0 = time.monotonic()
    for _ in range(rounds):
        add_and_sync("a", nb.port, na.port, make_round_records(k, USERS_A),
                     "a")
        answers.append(queries(nb.port))
        add_and_sync("b", na.port, nb.port, make_round_records(k, USERS_B),
                     "b")
        answers.append(queries(na.port))
    wall = time.monotonic() - t0
    na.srv.close()
    nb.srv.close()
    return answers, wall, repl_wire[0]


def part_b():
    print("\nPART B — fused vs off-the-shelf parts (two nodes, real wire"
          " both sides)\n")
    subprocess.run(["cc", "-O2", "-o", AMD,
                    os.path.join(ROOT, "native", "amd.c")], check=True)
    results = {}
    for regime, rounds, k in (("chatty", 40, 10), ("mid", 10, 100),
                              ("bulky", 4, 400)):
        f_walls, p_walls = [], []
        f_wire = p_wire = None
        for rep in range(3):
            global rng
            rng = random.Random(100 + rep)
            fa, fw, fwire = run_fused(rounds, k, 5000)
            rng = random.Random(100 + rep)
            pa, pw, pwire = run_parts(rounds, k, 5000)
            assert fa == pa, "stacks disagree in regime %s rep %d" % (
                regime, rep)
            f_walls.append(fw)
            p_walls.append(pw)
            f_wire, p_wire = fwire, pwire
        results[regime] = dict(
            rounds=rounds, per_round=k,
            fused_s=[round(x, 2) for x in sorted(f_walls)],
            parts_s=[round(x, 2) for x in sorted(p_walls)],
            fused_wire=f_wire, parts_wire=p_wire)
        rr = results[regime]
        print("  %s (%dx%d): fused %.2f-%.2fs  parts(sqlite) %.2f-%.2fs"
              "   wire: %d vs %d bytes   -> %s"
              % (regime, rounds, k, rr["fused_s"][0], rr["fused_s"][-1],
                 rr["parts_s"][0], rr["parts_s"][-1],
                 rr["fused_wire"], rr["parts_wire"],
                 "FUSED WINS" if rr["fused_s"][-1] < rr["parts_s"][0] else
                 "PARTS WIN" if rr["parts_s"][-1] < rr["fused_s"][0] else
                 "OVERLAP (no clear winner)"))
    print("\n  (answers asserted identical across stacks, every round,"
          " every repeat)")
    return results


def main():
    a = part_a()
    if a is None:
        return 1
    b = part_b()
    with open(os.path.join(ROOT, "phase19-results.json"), "w") as f:
        json.dump(dict(part_a=a, part_b=b), f, indent=1)
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
