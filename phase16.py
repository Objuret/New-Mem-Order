"""Phase 16 — the memory path: section 0's mechanism, finally measured.

The critique that chartered this phase (recorded via Jocke, 2026-07-09):
the point was always the machine's data path — a small structure set
resident in cache, traffic reduced to references + values — and no
prior phase measured the memory hierarchy at all. This one does.

native/membench.c streams the SAME logical records through the SAME
task kernel in two representations (conventional contiguous records vs
the real instruction grammar with an L1-sized resident template table)
and this driver measures, per recurrence ratio p:

  - stream bytes (what the memory system must move),
  - wall seconds (best of passes, compiled -O2),
  - D1 and LL cache misses (valgrind cachegrind: deterministic
    simulated hierarchy — perf counters are unavailable in this
    container; cache sizes pinned for reproducibility),

with results asserted identical across representations at every point.

The pre-stated falsification: at p=0 (no recurrence) the grammar is
pure overhead and reference-chasing may ADD misses; if the am form
does not win clearly as recurrence rises, section 0's residency story
has no mechanism.

Run from repo root: python3 phase16.py   (~2-4 minutes)
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(ROOT, "native", "membench")
N_TIME = 4_000_000     # ~250 MB raw stream: far beyond LL, streams from DRAM
N_MISS = 400_000       # cachegrind is ~50x slower; miss RATES are size-stable
PASSES = 3
SWEEP = [0, 50, 90, 99]
CG = ["valgrind", "--tool=cachegrind", "--cache-sim=yes", "--I1=32768,8,64",
      "--D1=32768,8,64", "--LL=8388608,16,64", "--cachegrind-out-file=/dev/null"]


def run(mode, p, n, passes):
    r = subprocess.run([BIN, mode, str(p), str(n), str(passes)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def misses(mode, p):
    r = subprocess.run(CG + [BIN, mode, str(p), str(N_MISS), "1"],
                       capture_output=True, text=True, check=True)
    d1 = ll = None
    for line in r.stderr.splitlines():
        if "D1  misses" in line or "D1 misses" in line:
            d1 = int(line.split(":")[1].split("(")[0].replace(",", "").strip())
        if "LL misses" in line and "LLi" not in line and "LLd" not in line:
            ll = int(line.split(":")[1].split("(")[0].replace(",", "").strip())
    assert d1 is not None and ll is not None, r.stderr[-800:]
    return d1, ll


def main():
    subprocess.run(["cc", "-O2", "-o", BIN,
                    os.path.join(ROOT, "native", "membench.c")], check=True)
    rows = []
    for p in SWEEP:
        raw = run("raw", p, N_TIME, PASSES)
        am = run("am", p, N_TIME, PASSES)
        assert (raw["sum"], raw["checksum"]) == (am["sum"], am["checksum"]), \
            "representations disagree at p=%d" % p
        raw_d1, raw_ll = misses("raw", p)
        am_d1, am_ll = misses("am", p)
        rows.append(dict(
            p=p,
            raw_mb=round(raw["stream_bytes"] / 1e6, 1),
            am_mb=round(am["stream_bytes"] / 1e6, 1),
            raw_s=raw["seconds"], am_s=am["seconds"],
            raw_ll_per_rec=round(raw_ll / N_MISS, 3),
            am_ll_per_rec=round(am_ll / N_MISS, 3),
            raw_d1_per_rec=round(raw_d1 / N_MISS, 3),
            am_d1_per_rec=round(am_d1 / N_MISS, 3),
        ))
        r = rows[-1]
        print("p=%3d%%  bytes: %6.1f -> %6.1f MB (%.2fx)   "
              "time: %.3f -> %.3f s (%.2fx)   "
              "LL misses/rec: %.3f -> %.3f (%.2fx)"
              % (p, r["raw_mb"], r["am_mb"], r["am_mb"] / r["raw_mb"],
                 r["raw_s"], r["am_s"], r["am_s"] / r["raw_s"],
                 r["raw_ll_per_rec"], r["am_ll_per_rec"],
                 (r["am_ll_per_rec"] / r["raw_ll_per_rec"])
                 if r["raw_ll_per_rec"] else 0))
    # the crux: when memory is the actual bottleneck, does traffic
    # reduction convert to time? Light kernel (8-byte xor loads: memory-
    # dominant), 4 concurrent streams contending for DRAM, kernel-only
    # per-pass seconds reported from inside each process (10 passes so
    # generation noise is excluded and contention overlaps).
    contended = []
    for p in (0, 99):
        agg = {}
        for mode in ("raw", "am"):
            procs = [subprocess.Popen(
                [BIN, mode, str(p), str(N_TIME), "10", "light"],
                stdout=subprocess.PIPE, text=True) for _ in range(4)]
            secs = []
            for pr in procs:
                out, _ = pr.communicate()
                secs.append(json.loads(out)["seconds"])
            agg[mode] = sum(secs) / len(secs)
        contended.append(dict(p=p, raw_s=round(agg["raw"], 4),
                              am_s=round(agg["am"], 4)))
        print("contended, memory-bound kernel, p=%3d%%:  raw %.3fs   "
              "am %.3fs   (%.2fx)"
              % (p, agg["raw"], agg["am"], agg["am"] / agg["raw"]))
    with open(os.path.join(ROOT, "phase16-results.json"), "w") as f:
        json.dump(dict(n_time=N_TIME, n_miss=N_MISS, rows=rows,
                       contended=contended), f, indent=1)
    print("\n(answers asserted identical across representations at every "
          "point; cachegrind hierarchy pinned: 32K L1d / 8MB LL)")
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
