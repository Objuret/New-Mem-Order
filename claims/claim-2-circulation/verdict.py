#!/usr/bin/env python3
"""Coded falsification conditions for claim 2 (MACHINE.md).

Claim: "Circulation beats program-mediated stepping. Whole-tree fused
firing vs one-operation-at-a-time with materialized intermediates:
time, instructions, and energy."

Judged side: the engine's plan circulation (its default execution).
Baseline: the engine's own walker - same arrangement, same stream,
one operation at a time with intermediates materialized at every node.
The jit path is reported as the compiled-ahead reference.

Rules (medians of REPS runs, ranges min..max):
  beat(D):     plan max < walker min (no overlap)
  PASS:        beat(D) at every measured depth AND the advantage ratio
               walker/plan at max depth exceeds the ratio at min depth
               (ceremony amortizes with depth - the predicted sign).
  FALSIFIED:   walker max < plan min at max depth (stepping decisively
               wins where circulation should win biggest).
  INCONCLUSIVE otherwise.

This host measures time only (no PMU, no joules) - recorded, not
glossed over.
"""
import json
import sys
from collections import defaultdict
from statistics import median


def main():
    raw, out_path = sys.argv[1], sys.argv[2]
    g = defaultdict(list)
    for line in open(raw):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        g[(r["depth"], r["variant"])].append(r["ns_per_elem"])
    stats = {k: {"med": median(v), "min": min(v), "max": max(v)}
             for k, v in g.items()}
    depths = sorted({d for d, _ in stats})

    table = {}
    for d in depths:
        w, p, j = stats[(d, "walker")], stats[(d, "plan")], stats[(d, "jit")]
        table[d] = {
            "walker": w, "plan": p, "jit": j,
            "ratio_walker_over_plan": w["med"] / p["med"],
            "ratio_walker_over_jit": w["med"] / j["med"],
            "beat": p["max"] < w["min"],
            "lose": w["max"] < p["min"],
        }

    dmin, dmax = depths[0], depths[-1]
    if table[dmax]["lose"]:
        verdict = "FALSIFIED"
        reason = f"walker decisively beats circulation at depth {dmax}"
    elif (all(table[d]["beat"] for d in depths)
          and table[dmax]["ratio_walker_over_plan"]
          > table[dmin]["ratio_walker_over_plan"]):
        verdict = "PASS"
        reason = (f"circulation beats stepping at every depth "
                  f"{dmin}..{dmax} with non-overlapping ranges; advantage "
                  f"grows from "
                  f"{table[dmin]['ratio_walker_over_plan']:.2f}x to "
                  f"{table[dmax]['ratio_walker_over_plan']:.2f}x "
                  f"(jit: {table[dmax]['ratio_walker_over_jit']:.2f}x)")
    else:
        verdict = "INCONCLUSIVE"
        reason = "no decisive result under the coded rules"

    result = {
        "claim": "2 - circulation beats program-mediated stepping",
        "verdict": verdict,
        "reason": reason,
        "accounting": "wall-time only (no PMU/joules on this host)",
        "table_ns_per_elem": {
            str(d): {k: ({kk: round(vv, 3) for kk, vv in v.items()}
                         if isinstance(v, dict) else round(v, 3))
                     for k, v in t.items()}
            for d, t in table.items()},
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nCLAIM 2 VERDICT: {verdict}")
    print(reason)
    print(f"\n{'depth':>6} {'walker':>9} {'plan':>9} {'jit':>9} "
          f"{'w/plan':>7} {'w/jit':>7} beat")
    for d in depths:
        t = table[d]
        print(f"{d:>6} {t['walker']['med']:>9.2f} {t['plan']['med']:>9.2f} "
              f"{t['jit']['med']:>9.2f} "
              f"{t['ratio_walker_over_plan']:>6.2f}x "
              f"{t['ratio_walker_over_jit']:>6.2f}x "
              f"{'YES' if t['beat'] else ('lose' if t['lose'] else 'tie')}")


if __name__ == "__main__":
    main()
