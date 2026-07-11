#!/usr/bin/env python3
"""Coded falsification conditions for claim 3 (MACHINE.md).

Claim: "Exits-only collapses traffic. Bytes crossing the core/memory
and node/node boundaries, staged vs circulating: ratio ~ intermediates
over exits."

Both byte counts are code-side measurements from the same bench run,
with decode parity enforced (the exits-only wire reconstructs the
staged pipeline's values exactly, or the bench aborts).

Rules, per (depth, dist) configuration with D intermediates and 1 exit:
  predicted ratio (unique streams): D stages x 8B vs <=12B per exit
                                    => ~ 2D/3, i.e. "~ intermediates
                                    over exits" up to the naming header
  PASS:        measured ratio >= D/2 in every configuration (the
               order-of-magnitude claim holds), and recurrent streams
               show a strictly higher ratio than unique ones at equal
               depth (names collapse recurrence further).
  FALSIFIED:   any configuration with ratio < 1 (exits-only moved MORE
               bytes than staging).
  INCONCLUSIVE otherwise.
"""
import json
import sys


def main():
    raw, out_path = sys.argv[1], sys.argv[2]
    rows = [json.loads(l) for l in open(raw) if l.strip()]

    checks, failed, inconclusive = [], False, False
    by_depth = {}
    for r in rows:
        d, ratio = r["depth"], r["ratio"]
        ok = ratio >= d / 2
        if ratio < 1:
            failed = True
        if not ok:
            inconclusive = True
        by_depth.setdefault(d, {})[r["dist"]] = ratio
        checks.append({
            "depth": d, "dist": r["dist"], "measured_ratio": ratio,
            "threshold_D_over_2": d / 2, "ok": ok,
            "staged_bytes": r["staged_bytes"],
            "exit_bytes": r["exit_bytes"],
        })
    recurrence_amplifies = all(
        v.get("recurrent", 0) > v.get("unique", 0)
        for v in by_depth.values())

    if failed:
        verdict = "FALSIFIED"
        reason = "exits-only moved more bytes than staging somewhere"
    elif not inconclusive and recurrence_amplifies:
        verdict = "PASS"
        rs = {d: (round(v["unique"], 1), round(v["recurrent"], 1))
              for d, v in sorted(by_depth.items())}
        reason = (f"traffic ratio tracks intermediates-over-exits at every "
                  f"depth and recurrence amplifies it: "
                  f"{{depth: (unique, recurrent)}} = {rs}")
    else:
        verdict = "INCONCLUSIVE"
        reason = ("ratio fell below D/2 somewhere, or recurrence failed "
                  "to amplify")

    result = {
        "claim": "3 - exits-only collapses traffic",
        "verdict": verdict,
        "reason": reason,
        "configs": checks,
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nCLAIM 3 VERDICT: {verdict}")
    print(reason)
    print(f"\n{'depth':>6} {'dist':>10} {'staged MB':>10} {'exit MB':>9} "
          f"{'ratio':>8} {'>=D/2':>6}")
    for c in checks:
        print(f"{c['depth']:>6} {c['dist']:>10} "
              f"{c['staged_bytes'] / 1e6:>10.1f} "
              f"{c['exit_bytes'] / 1e6:>9.2f} "
              f"{c['measured_ratio']:>7.1f}x "
              f"{'YES' if c['ok'] else 'NO':>6}")


if __name__ == "__main__":
    main()
