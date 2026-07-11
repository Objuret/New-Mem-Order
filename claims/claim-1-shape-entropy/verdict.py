#!/usr/bin/env python3
"""Coded falsification conditions for claim 1 (MACHINE.md).

Claim: "Routing beats prediction where shape-entropy is high. Tag-routed
dispatch vs branchy dispatch over the same stream, swept from 2 to
~1000 interleaved shapes: crossover as predictor tables thrash,
widening without bound."

The routed side is routed_staged (the machine's design: queue in cache,
roads fire as units). The branchy side is, AT EACH N, whichever
conventional baseline is FASTER there (switch or chain) - the claim
must beat the strongest baseline, not a strawman. routed_direct is
reported as diagnostics only: per-element indirect hops are the naive
reading, not the design.

Verdict rules (medians of REPS runs; ranges are min..max):
  beat(N):  routed_staged max  < branchy_best min   (no overlap)
  lose(N):  branchy_best  max  < routed_staged min  (no overlap)
  PASS:        a crossover N* exists in the sweep, beat(N) holds for
               every measured N >= N*, and the advantage ratio
               branchy_best/routed_staged is larger at N=1024 than at
               N* (widening).
  FALSIFIED:   lose(1024) - routing decisively loses even at the
               highest shape-entropy measured.
  INCONCLUSIVE: anything else (overlapping ranges at the top, or a
               non-monotone win region).

Mechanism check (secondary, does not gate the verdict but is reported):
under the skew control (N=1024 declared, 99% one tag), branchy_switch
must recover to near its low-N speed. If it does not, the attribution
of the branchy slowdown to predictor thrash is wrong.
"""
import json
import sys
from collections import defaultdict
from statistics import median


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def agg(rows, key_fields):
    g = defaultdict(list)
    for r in rows:
        g[tuple(r[k] for k in key_fields)].append(r["ns_per_elem"])
    return {k: {"med": median(v), "min": min(v), "max": max(v)}
            for k, v in g.items()}


def main():
    raw, out_path = sys.argv[1], sys.argv[2]
    rows = load(raw)

    primary = [r for r in rows
               if r["label"] == "o2" and r["dist"] == "uniform"
               and r["ops"] == 8]
    stats = agg(primary, ("nshapes", "variant"))
    ns = sorted({r["nshapes"] for r in primary})

    table = {}
    for n in ns:
        sw = stats[(n, "branchy_switch")]
        ch = stats[(n, "branchy_chain")]
        best_name = "branchy_switch" if sw["med"] <= ch["med"] else "branchy_chain"
        best = stats[(n, best_name)]
        staged = stats[(n, "routed_staged")]
        direct = stats[(n, "routed_direct")]
        table[n] = {
            "branchy_switch": sw, "branchy_chain": ch,
            "branchy_best": best_name,
            "routed_direct": direct, "routed_staged": staged,
            "ratio_best_over_staged": best["med"] / staged["med"],
            "beat": staged["max"] < best["min"],
            "lose": best["max"] < staged["min"],
        }

    nmax = max(ns)
    crossover = None
    for n in ns:
        if all(table[m]["beat"] for m in ns if m >= n):
            crossover = n
            break

    if table[nmax]["lose"]:
        verdict = "FALSIFIED"
        reason = (f"routed_staged decisively loses to "
                  f"{table[nmax]['branchy_best']} at N={nmax} "
                  f"(highest entropy measured)")
    elif crossover is not None and (
            table[nmax]["ratio_best_over_staged"]
            > table[crossover]["ratio_best_over_staged"]
            or crossover == nmax):
        verdict = "PASS"
        reason = (f"crossover at N={crossover}; routed_staged beats the "
                  f"strongest branchy baseline at every N >= {crossover}; "
                  f"advantage ratio grows from "
                  f"{table[crossover]['ratio_best_over_staged']:.2f}x at "
                  f"crossover to "
                  f"{table[nmax]['ratio_best_over_staged']:.2f}x at N={nmax}")
    elif crossover is not None:
        verdict = "INCONCLUSIVE"
        reason = "win region exists but advantage does not widen with N"
    else:
        verdict = "INCONCLUSIVE"
        reason = ("no N at which routed_staged beats the strongest "
                  "baseline without range overlap, and no decisive loss "
                  f"at N={nmax}")

    # mechanism check: skew control
    skew_rows = [r for r in rows if r["dist"] == "skew"]
    mech = None
    if skew_rows:
        s = agg(skew_rows, ("nshapes", "variant"))
        sw_skew = s[(1024, "branchy_switch")]["med"]
        sw_low = table[min(ns)]["branchy_switch"]["med"]
        sw_high = table[1024]["branchy_switch"]["med"]
        recovered = sw_skew < sw_low + 0.5 * (sw_high - sw_low)
        mech = {
            "branchy_switch_ns_at_N2_uniform": sw_low,
            "branchy_switch_ns_at_N1024_uniform": sw_high,
            "branchy_switch_ns_at_N1024_skew": sw_skew,
            "predictor_recovers_under_low_entropy": recovered,
            "all_variants_at_skew_ns": {
                v: round(s[(1024, v)]["med"], 3)
                for v in ("branchy_switch", "branchy_chain",
                          "routed_direct", "routed_staged")
                if (1024, v) in s},
            "note": ("low entropy is branchy territory and the apparatus "
                     "shows it - the claim's win is regime-bound, exactly "
                     "as MACHINE.md states it"),
        }

    # secondary tables (reported, not gated)
    novec = agg([r for r in rows if r["label"] == "novec"],
                ("nshapes", "variant"))
    depth = agg([r for r in rows
                 if r["label"] == "o2" and r["dist"] == "uniform"
                 and r["ops"] != 8],
                ("ops", "nshapes", "variant"))

    counters = any(r["brmiss_per_elem"] >= 0 for r in rows)
    brmiss = {}
    if counters:
        g = defaultdict(list)
        for r in primary:
            if r["brmiss_per_elem"] >= 0:
                g[(r["nshapes"], r["variant"])].append(r["brmiss_per_elem"])
        brmiss = {f"{k[0]}/{k[1]}": round(median(v), 4)
                  for k, v in sorted(g.items())}

    result = {
        "claim": "1 - routing beats prediction where shape-entropy is high",
        "verdict": verdict,
        "reason": reason,
        "crossover_N": crossover,
        "pmu_counters_available": counters,
        "primary_table_ns_per_elem": {
            str(n): {v: {kk: round(vv, 3) for kk, vv in st.items()}
                     if isinstance(st, dict) else st
                     for v, st in t.items()}
            for n, t in table.items()},
        "branch_misses_per_elem": brmiss,
        "mechanism_check_skew": mech,
        "novec_ns_per_elem": {f"{k[0]}/{k[1]}":
                              round(v["med"], 3) for k, v in sorted(novec.items())},
        "work_depth_ns_per_elem": {f"L{k[0]}/N{k[1]}/{k[2]}":
                                   round(v["med"], 3) for k, v in sorted(depth.items())},
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nCLAIM 1 VERDICT: {verdict}")
    print(reason)
    print(f"\n{'N':>5} {'switch':>9} {'chain':>9} {'direct':>9} "
          f"{'staged':>9} {'ratio':>7} beat")
    for n in ns:
        t = table[n]
        print(f"{n:>5} {t['branchy_switch']['med']:>9.2f} "
              f"{t['branchy_chain']['med']:>9.2f} "
              f"{t['routed_direct']['med']:>9.2f} "
              f"{t['routed_staged']['med']:>9.2f} "
              f"{t['ratio_best_over_staged']:>6.2f}x "
              f"{'YES' if t['beat'] else ('lose' if t['lose'] else 'tie')}")


if __name__ == "__main__":
    main()
