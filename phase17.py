"""Phase 17 — amx: the engine designed FOR the machine, measured.

Jocke's charge (2026-07-09/10): nothing before this was BUILT the way
the model says the machine should work — amd (phase 14) was a faithful
C translation of the Python architecture: a file per instruction, an
open() per demand, a copy per value. The residual it measured (~7x
behind the best conventional design on record-granular work) was the
cost of that LAYOUT, not of the model.

native/amx.c is the section-8 realization proper (DECISIONS 2.4,
ruled):

  - the world is ONE mmap'd append-only pack; a reference is an
    offset-name ("@1f4a") and demanding it is pointer arithmetic — no
    syscall, no inode;
  - values are slices (a literal fires to a pointer into the pack; a
    resident template fires to a pointer into the library blob); bytes
    are copied at most once, into a per-request bump arena;
  - emit with the reserved name "@" appends to the pack and returns
    the assigned offset-name — the demander holds the returned
    reference, which is the phase-1 pattern made physical.

Grammar, structure set, wire protocol: byte-compatible with every
prior phase.

The honest consequence, stated up front: offset references are
assigned by the store, so a chain writer cannot pipeline blindly —
each link embeds the offset the previous emit RETURNED. Ingest here
is round-trip-per-record while amd/conv ingest is fully pipelined;
that asymmetry is the model's own data dependency and is reported,
not hidden.

Gates before any clock:
  1. answers byte-identical across all four pipelines
     (conv log+scan, conv indexed, model amd, model amx);
  2. full chain renders from the pack equal the Python-computed text;
  3. amx refuses like the model refuses (div by zero, dangling offset,
     malformed offset, garbage on the wire);
  4. kill -9 mid-life, restart: same answers (tail side-file recovery);
  5. the tail side-file is DERIVABLE state: walking the pack from 0
     with the grammar's skip() reproduces it exactly.

Then the phase-13/14 job with true clocks, amx beside the other three.

Run from repo root: python3 phase17.py
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
WORK = os.path.join(ROOT, "phase17")
BIN = os.path.join(ROOT, "native", "amx")

sys.path.insert(0, ROOT)
os.makedirs(WORK, exist_ok=True)
import phase13
import phase14
phase13.WORK = WORK
phase14.WORK = WORK
from phase13 import make_records, THRESH, USERS
from phase14 import build_conv, build_model, pipelined, run_am, run_conv, \
    wait_port
from am.instruction import Incomplete, comp, demand, lit, outcome, skip
from am.structures import CONCAT, EMIT_DISK, PICK, SUM, TALLY

NL = lit("\n")
PORTS = iter(range(7961, 7999))
WORLD = os.path.join(WORK, "world-amx")


def start_amx(port, fresh=False):
    if fresh:
        shutil.rmtree(WORLD, ignore_errors=True)
    proc = subprocess.Popen([BIN, WORLD, str(port)],
                            stderr=subprocess.DEVNULL)
    wait_port(port, proc)
    return proc


def call_one(f, instr):
    f.write(instr)
    f.flush()
    buf = b""
    while True:
        try:
            end = skip(buf, 0)
            break
        except Incomplete:
            data = f.read1(65536)
            assert data, "amx closed the connection"
            buf += data
    return outcome(buf[:end])


def ingest_amx(port, records):
    """One writer, one connection. Every chain link demands the offset
    the previous emit RETURNED, so this is round-trip-per-record by
    construction — the data dependency of store-assigned names."""
    heads_rec, heads_amt = {}, {}
    with socket.create_connection(("127.0.0.1", port)) as s, \
            s.makefile("rwb") as f:
        t0 = time.monotonic()
        for u in USERS:
            kind, val = call_one(f, comp(
                CONCAT,
                comp(EMIT_DISK, lit("@"), lit(lit(b""))),
                comp(EMIT_DISK, lit("@"), lit(lit(b"")))))
            assert kind == "value", val
            _, r, a = val.split(b"@")
            heads_rec[u], heads_amt[u] = "@" + r.decode(), "@" + a.decode()
        for rec in records:
            u = rec["user"]
            recfile = comp(CONCAT, demand(heads_rec[u]),
                           lit("%s %d %s\n" % (u, rec["amount"], rec["note"])))
            amtfile = comp(CONCAT, demand(heads_amt[u]),
                           lit("%d\n" % rec["amount"]))
            kind, val = call_one(f, comp(
                CONCAT,
                comp(EMIT_DISK, lit("@"), lit(recfile)),
                comp(EMIT_DISK, lit("@"), lit(amtfile))))
            assert kind == "value", val
            _, r, a = val.split(b"@")
            heads_rec[u], heads_amt[u] = "@" + r.decode(), "@" + a.decode()
        t_ingest = time.monotonic() - t0
    return heads_rec, heads_amt, t_ingest


def build_queries(heads_amt):
    q = []
    for u in USERS:
        q.append(comp(SUM, demand(heads_amt[u]), NL))
        q.append(comp(TALLY, comp(PICK, demand(heads_amt[u]), NL,
                                  lit("ge"), lit(str(THRESH))), NL, lit("")))
    return q


def query_amx(port, queries):
    resp, t = pipelined(port, queries, "am")
    answers = []
    for r in resp:
        kind, val = outcome(r)
        assert kind == "value", val
        answers.append(int(val))
    return answers, t


def refusal_gate(port):
    from am.sync import call
    k, v = call("127.0.0.1", port, comp(8, lit("1"), lit("0")))
    assert k == "error" and b"division by zero" in v, (k, v)
    k, v = call("127.0.0.1", port, demand("@ffffffff"))
    assert k == "error" and b"no such reference" in v, (k, v)
    k, v = call("127.0.0.1", port, demand("@zz"))
    assert k == "error" and b"bad offset reference" in v, (k, v)
    k, v = call("127.0.0.1", port, b"\x09garbage")
    assert k == "error", (k, v)


def walk_tail(packpath):
    """Derive the tail with the grammar alone: skip() from 0 until the
    remainder is no longer a whole instruction."""
    with open(packpath, "rb") as f:
        pack = f.read()
    off = 0
    while off < len(pack):
        try:
            off = skip(pack, off)
        except Exception:
            break
    return off


def main():
    subprocess.run(["cc", "-O2", "-o", BIN,
                    os.path.join(ROOT, "native", "amx.c")], check=True)
    subprocess.run(["cc", "-O2", "-o", os.path.join(ROOT, "native", "amd"),
                    os.path.join(ROOT, "native", "amd.c")], check=True)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    records = make_records()
    payload = sum(len(json.dumps(r)) for r in records)
    expected_rec = {u: "".join(
        "%s %d %s\n" % (u, r["amount"], r["note"])
        for r in records if r["user"] == u) for u in USERS}

    # ---- amx: ingest, gates ------------------------------------------------
    port = next(PORTS)
    proc = start_amx(port, fresh=True)
    refusal_gate(port)
    heads_rec, heads_amt, ti_amx = ingest_amx(port, records)
    queries = build_queries(heads_amt)
    a_amx, tq_amx = query_amx(port, queries)

    # gate 2: the full record chain renders byte-identically from the pack
    with socket.create_connection(("127.0.0.1", port)) as s, \
            s.makefile("rwb") as f:
        for u in USERS:
            kind, val = call_one(f, demand(heads_rec[u]))
            assert kind == "value" and val.decode() == expected_rec[u], \
                "chain render diverged for %s" % u
    print("gate: chain renders byte-identical to expected text (5 users)")

    # gate 4: kill -9, restart, same answers
    proc.send_signal(signal.SIGKILL)
    proc.wait()
    port2 = next(PORTS)
    t0 = time.monotonic()
    proc = start_amx(port2)
    t_restart = time.monotonic() - t0
    a_again, _ = query_amx(port2, build_queries(heads_amt))
    assert a_again == a_amx, "answers changed across kill -9 + restart"
    print("gate: kill -9 + restart, answers identical (recovery %.3fs)"
          % t_restart)
    proc.send_signal(signal.SIGTERM)
    proc.wait()

    # gate 5: the tail side-file is derivable from the pack alone
    derived = walk_tail(os.path.join(WORLD, "pack"))
    with open(os.path.join(WORLD, "tail")) as f:
        saved = int(f.read(), 16)
    assert derived == saved, (derived, saved)
    print("gate: tail side-file (%d) == grammar walk of the pack" % saved)

    # ---- the other three pipelines (phase-14 methodology, same run) --------
    conv_adds, conv_q, _ = build_conv(records)
    am_adds, am_q, t_build_am = build_model(records)
    a_log, ti_log, tq_log = run_conv(records, conv_adds, conv_q, False)
    a_idx, ti_idx, tq_idx = run_conv(records, conv_adds, conv_q, True)
    a_amd, ti_amd, tq_amd, world_amd = run_am(am_adds, am_q, native=True)
    assert a_log == a_idx == a_amd == a_amx, "pipelines disagree"
    print("gate: answers identical across all four pipelines\n")

    pack_bytes = saved
    amd_bytes = sum(os.path.getsize(os.path.join(d, n))
                    for d, _, ns in os.walk(world_amd) for n in ns)
    amd_files = sum(len(ns) for _, _, ns in os.walk(world_amd))
    amx_files = sum(len(ns) for _, _, ns in os.walk(WORLD))

    print("TRUE BENCHMARK — same job (%d records, %.2f MB payload, %d queries)"
          % (len(records), payload / 1e6, len(queries)))
    print("  (amx ingest is round-trip-per-record — store-assigned names are"
          "\n   a data dependency; the other three are fully pipelined)\n")
    print("  %-24s %12s %12s %12s %12s"
          % ("seconds", "conv log", "conv idx", "model amd", "model amx"))
    print("  %-24s %12.3f %12.3f %12.3f %12.3f"
          % ("ingest", ti_log, ti_idx, ti_amd + t_build_am, ti_amx))
    print("  %-24s %12.3f %12.3f %12.3f %12.3f"
          % ("queries (10)", tq_log, tq_idx, tq_amd, tq_amx))
    print("\n  store: amd %d files / %.2f MB   amx %d files / %.2f MB (pack)"
          % (amd_files, amd_bytes / 1e6, amx_files, pack_bytes / 1e6))
    print("  restart to first answer: %.3fs" % t_restart)

    results = dict(
        records=len(records), payload_bytes=payload,
        ingest_s=dict(conv_log=round(ti_log, 3), conv_idx=round(ti_idx, 3),
                      model_amd=round(ti_amd + t_build_am, 3),
                      model_amx=round(ti_amx, 3)),
        query_s=dict(conv_log=round(tq_log, 4), conv_idx=round(tq_idx, 4),
                     model_amd=round(tq_amd, 4), model_amx=round(tq_amx, 4)),
        store=dict(amd_files=amd_files, amd_bytes=amd_bytes,
                   amx_files=amx_files, amx_pack_bytes=pack_bytes),
        restart_s=round(t_restart, 4),
    )
    with open(os.path.join(ROOT, "phase17-results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
