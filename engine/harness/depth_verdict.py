#!/usr/bin/env python3
"""Depth-scaling check over circulate runs (S = 1, 2, 4, 8).

Layer-4 prediction: per-stage ceremony is what circulation deletes, so
the machine's advantage over the materializing pipeline must GROW with
depth, and pure circulation must track (or beat) compiled fusion at
every depth. Coded:
  PASS: ratio(pipeline/circulating) strictly increases with S, and
        circulating <= fused * 1.1 at every S (tracks fusion), and
        the full machine beats the strongest conventional at every S
        with trimmed ranges disjoint.
  FALSIFIED: the pipeline advantage ratio shrinks as S grows.
  INCONCLUSIVE otherwise.
"""
import json
import sys

rows = [json.loads(l)["circulation"] for l in open(sys.argv[1]) if l.strip()]
rows.sort(key=lambda r: r["stream"]["stages"])

table, ratios, ok_fused, ok_win = [], [], True, True
for r in rows:
    S = r["stream"]["stages"]
    m = r["machine_account"]
    b = r["baseline_account"]
    circ, mat = m["circulating"], m["circulating+matrix"]
    ratio = b["bl_pipeline"]["mean"] / circ["mean"]
    ratios.append(ratio)
    if circ["mean"] > b["bl_fused"]["mean"] * 1.1:
        ok_fused = False
    if r["verdict"] != "WIN":
        ok_win = False
    table.append((S, circ["mean"], mat["mean"], b["bl_pipeline"]["mean"],
                  b["bl_fused"]["mean"], b["bl_fused_hashed"]["mean"],
                  ratio, r["verdict"]))

grows = all(ratios[i] < ratios[i + 1] for i in range(len(ratios) - 1))
shrinks = all(ratios[i] > ratios[i + 1] for i in range(len(ratios) - 1))
verdict = ("PASS" if grows and ok_fused and ok_win
           else "FALSIFIED" if shrinks else "INCONCLUSIVE")

print(f"DEPTH-SCALING VERDICT: {verdict}")
print(f"{'S':>3} {'circ':>7} {'machine':>8} {'pipeline':>9} {'fused':>7} "
      f"{'fus+hash':>9} {'pipe/circ':>10} {'verdict':>8}")
for t in table:
    print(f"{t[0]:>3} {t[1]:>7.2f} {t[2]:>8.2f} {t[3]:>9.2f} {t[4]:>7.2f} "
          f"{t[5]:>9.2f} {t[6]:>9.2f}x {t[7]:>8}")
out = {"depth_scaling_verdict": verdict,
       "pipeline_over_circulating_by_stage": ratios,
       "per_stage": [json.loads(l)["circulation"]
                     for l in open(sys.argv[1]) if l.strip()]}
json.dump(out, open(sys.argv[2], "w"), indent=2)
