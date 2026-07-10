"""Phase 14 — the real build: amd, a native router, and true benchmarks.

native/amd.c is the complete section-8 realization for everything the
benchmarks exercise: full grammar, all 11 universal structures, the
emit terminal, resident templates, the phase-1 wire protocol, one
event loop. Byte-compatible with every world the Python runtime wrote.

Correctness gates before any timing:
  1. identical ingest through the Python router and through amd must
     leave BYTE-IDENTICAL world trees (the write path, cross-language);
  2. all query answers byte-identical across every pipeline;
  3. amd refuses like the model refuses (division by zero, missing
     reference, garbage on the wire).

Then the phase-13 job again with honest clocks: all four pipelines get
pre-built wire bytes (construction timed separately per side) and all
four are pipelined the same way — send everything, then read every
response. The crossings/copies byte counts are phase 13's; this phase
adds the wall-clock rows that phase 13 could not honestly provide.

Run from repo root: python3 phase14.py
"""

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "phase14")
BIN = os.path.join(ROOT, "native", "amd")

sys.path.insert(0, ROOT)
os.makedirs(WORK, exist_ok=True)
import phase13
phase13.WORK = WORK
from phase13 import ConvServer, make_records, USERS, THRESH
from am.instruction import Incomplete, comp, demand, lit, outcome, skip
from am.structures import CONCAT, EMIT_DISK, PICK, SUM, TALLY

NL = lit("\n")
PORTS = iter(range(7891, 7960))


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


def pipelined(port, requests, framing):
    """Send every request, then read every response. framing='json' or 'am'."""
    out = []
    with socket.create_connection(("127.0.0.1", port)) as s:
        t0 = time.monotonic()
        s.sendall(b"".join(requests))
        buf = b""
        while len(out) < len(requests):
            if framing == "json":
                nl = buf.find(b"\n")
                if nl >= 0:
                    out.append(buf[:nl + 1])
                    buf = buf[nl + 1:]
                    continue
            else:
                try:
                    end = skip(buf, 0)
                    out.append(buf[:end])
                    buf = buf[end:]
                    continue
                except Incomplete:
                    pass
            data = s.recv(1 << 20)
            assert data, "server closed early"
            buf += data
        return out, time.monotonic() - t0


# ---- pre-built wire bytes (construction timed separately) ----------------

def build_conv(records):
    t0 = time.monotonic()
    adds = [(json.dumps(dict(op="add", **r)) + "\n").encode() for r in records]
    queries = []
    for u in USERS:
        for op in ("total", "count_ge"):
            queries.append((json.dumps(dict(op=op, user=u, t=THRESH)) + "\n").encode())
    return adds, queries, time.monotonic() - t0


def build_model(records):
    t0 = time.monotonic()
    adds = []
    prev_rec = {}
    prev_amt = {}
    seq = {u: 0 for u in USERS}
    for u in USERS:
        adds.append(comp(CONCAT,
                         comp(EMIT_DISK, lit("rec/%s-g" % u), lit(lit(b""))),
                         comp(EMIT_DISK, lit("amt/%s-g" % u), lit(lit(b"")))))
        prev_rec[u], prev_amt[u] = "rec/%s-g" % u, "amt/%s-g" % u
    for r in records:
        u = r["user"]
        n = seq[u]
        seq[u] += 1
        rref, aref = "rec/%s-%d" % (u, n), "amt/%s-%d" % (u, n)
        adds.append(comp(CONCAT,
                         comp(EMIT_DISK, lit(rref), lit(
                             comp(CONCAT, demand(prev_rec[u]),
                                  lit("%s %d %s\n" % (u, r["amount"], r["note"]))))),
                         comp(EMIT_DISK, lit(aref), lit(
                             comp(CONCAT, demand(prev_amt[u]),
                                  lit("%d\n" % r["amount"]))))))
        prev_rec[u], prev_amt[u] = rref, aref
    queries = []
    for u in USERS:
        chain = prev_amt[u]
        queries.append(comp(SUM, demand(chain), NL))
        queries.append(comp(TALLY, comp(PICK, demand(chain), NL, lit("ge"),
                                        lit(str(THRESH))), NL, lit("")))
    return adds, queries, time.monotonic() - t0


# ---- pipeline runners -----------------------------------------------------

def run_conv(records, adds, queries, projected):
    port = next(PORTS)
    server = ConvServer(phase13.Counters(), projected=projected, port=port)
    server.start()
    wait_port(port)
    _, t_ingest = pipelined(port, adds, "json")
    resp, t_query = pipelined(port, queries, "json")
    server.sock.close()
    answers = [json.loads(r)["value"] for r in resp]
    return answers, t_ingest, t_query


def run_am(adds, queries, native):
    port = next(PORTS)
    world = os.path.join(WORK, "world-" + ("amd" if native else "py"))
    shutil.rmtree(world, ignore_errors=True)
    if native:
        proc = subprocess.Popen([BIN, world, str(port)],
                                stderr=subprocess.DEVNULL)
    else:
        proc = subprocess.Popen(
            [sys.executable, "-m", "am.router", "--world", world,
             "--port", str(port), "--stats", os.devnull],
            cwd=ROOT, stderr=subprocess.DEVNULL)
    wait_port(port, proc)
    try:
        acks, t_ingest = pipelined(port, adds, "am")
        assert all(a[0] == 0x01 for a in acks), "an emit refused"
        resp, t_query = pipelined(port, queries, "am")
        answers = []
        for r in resp:
            kind, val = outcome(r)
            assert kind == "value", val
            answers.append(int(val))
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait()
    return answers, t_ingest, t_query, world


def tree_hash(base):
    h = hashlib.sha256()
    for dirpath, dirs, names in sorted(os.walk(base)):
        dirs.sort()
        for name in sorted(names):
            p = os.path.join(dirpath, name)
            h.update(os.path.relpath(p, base).encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def refusal_gate():
    port = next(PORTS)
    world = os.path.join(WORK, "world-refusals")
    shutil.rmtree(world, ignore_errors=True)
    proc = subprocess.Popen([BIN, world, str(port)], stderr=subprocess.DEVNULL)
    wait_port(port, proc)
    from am.sync import call
    try:
        k, v = call("127.0.0.1", port, comp(8, lit("1"), lit("0")))   # div
        assert k == "error" and b"division by zero" in v, (k, v)
        k, v = call("127.0.0.1", port, demand("nope"))
        assert k == "error" and b"no such reference" in v, (k, v)
        k, v = call("127.0.0.1", port, b"\x09garbage")
        assert k == "error", (k, v)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait()


def main():
    subprocess.run(["cc", "-O2", "-o", BIN,
                    os.path.join(ROOT, "native", "amd.c")], check=True)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    records = make_records()
    payload = sum(len(json.dumps(r)) for r in records)

    conv_adds, conv_q, t_build_conv = build_conv(records)
    am_adds, am_q, t_build_am = build_model(records)

    refusal_gate()
    a_log, ti_log, tq_log = run_conv(records, conv_adds, conv_q, False)
    a_idx, ti_idx, tq_idx = run_conv(records, conv_adds, conv_q, True)
    a_py, ti_py, tq_py, world_py = run_am(am_adds, am_q, native=False)
    a_amd, ti_amd, tq_amd, world_amd = run_am(am_adds, am_q, native=True)

    assert a_log == a_idx == a_py == a_amd, "pipelines disagree"
    assert tree_hash(world_py) == tree_hash(world_amd), \
        "python and amd wrote different worlds"
    print("gates: PASS (answers identical across 4 pipelines; Python and amd"
          " ingests left byte-identical world trees; amd refuses correctly)\n")

    def row(name, *vals):
        print(("  %-22s" + " %12s" * len(vals))
              % (name, *("%.3f" % v for v in vals)))

    print("TRUE BENCHMARK — same job (%d records, %.2f MB payload, %d queries)\n"
          % (len(records), payload / 1e6, len(am_q)))
    print("  %-22s %12s %12s %12s %12s"
          % ("seconds", "conv log", "conv idx", "model py", "model amd"))
    row("construction", t_build_conv, t_build_conv, t_build_am, t_build_am)
    row("ingest", ti_log, ti_idx, ti_py, ti_amd)
    row("queries (10)", tq_log, tq_idx, tq_py, tq_amd)
    row("total", t_build_conv + ti_log + tq_log,
        t_build_conv + ti_idx + tq_idx,
        t_build_am + ti_py + tq_py, t_build_am + ti_amd + tq_amd)
    print("\n  crossings/copies per byte are phase 13's (byte counts,"
          " language-independent):\n  14.15/15.62 log+scan, 2.68/4.02 indexed,"
          " 1.79/3.27 model")
    results = dict(
        records=len(records), payload_bytes=payload,
        construction_s=dict(conv=round(t_build_conv, 3), model=round(t_build_am, 3)),
        ingest_s=dict(conv_log=round(ti_log, 3), conv_idx=round(ti_idx, 3),
                      model_py=round(ti_py, 3), model_amd=round(ti_amd, 3)),
        query_s=dict(conv_log=round(tq_log, 3), conv_idx=round(tq_idx, 3),
                     model_py=round(tq_py, 3), model_amd=round(tq_amd, 3)),
    )
    with open(os.path.join(ROOT, "phase14-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
