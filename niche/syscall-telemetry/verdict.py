#!/usr/bin/env python3
"""Coded verdict for the niche head-to-head (MACHINE.md kill-list:
"the engine must win one niche on measured advantage"; kill condition:
"real-world recurrence and shape-entropy too low for the routed and
memoized layers to pay").

Judged: eng_jit (the full machine: jit roads + result matrix).
Opponent: the STRONGER of bl_switch and bl_memo at their medians -
the memoized baseline exists precisely so the engine cannot win by
bringing a technique the baseline was denied.

  WIN:          eng_jit max < opponent min (non-overlapping ranges).
  LOSS:         opponent max < eng_jit min - on this real traffic the
                machine does not pay; kill-condition evidence, record
                it as such.
  INCONCLUSIVE: overlap.

The stream's own statistics (entropy, recurrence) are attached to the
verdict either way: they are the regime facts that explain the result.
"""
import json
import sys
from collections import defaultdict
from statistics import median


def main():
    raw, stats_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    stream = json.load(open(stats_path))
    g = defaultdict(list)
    cold = {}
    for line in open(raw):
        r = json.loads(line)
        if r.get("cold"):
            cold[r["variant"]] = r
        else:
            g[r["variant"]].append(r["ns_per_elem"])
    st = {k: {"med": median(v), "min": min(v), "max": max(v)}
          for k, v in g.items()}

    opp_name = min(("bl_switch", "bl_memo"), key=lambda k: st[k]["med"])
    opp, eng = st[opp_name], st["eng_jit"]

    if eng["max"] < opp["min"]:
        verdict = "WIN"
        reason = (f"the full machine beats the strongest conventional "
                  f"baseline ({opp_name}) on real traffic: "
                  f"{eng['med']:.2f} vs {opp['med']:.2f} ns/event "
                  f"({opp['med'] / eng['med']:.2f}x), ranges disjoint")
    elif opp["max"] < eng["min"]:
        verdict = "LOSS"
        reason = (f"{opp_name} beats the machine on real traffic: "
                  f"{opp['med']:.2f} vs {eng['med']:.2f} ns/event. "
                  f"This is kill-condition evidence at this traffic's "
                  f"operating point (entropy "
                  f"{stream['tag_entropy_bits']} bits, recurrence "
                  f"{stream['value_recurrence']:.1%}) - record, do not "
                  f"reinterpret")
    else:
        verdict = "INCONCLUSIVE"
        reason = "ranges overlap"

    result = {
        "niche": "syscall telemetry enrichment over real program traces",
        "verdict": verdict,
        "reason": reason,
        "opponent": opp_name,
        "steady_state_ns_per_event": {
            k: {kk: round(vv, 3) for kk, vv in v.items()}
            for k, v in sorted(st.items())},
        "cold_pass": cold,
        "stream": {k: stream[k] for k in
                   ("events", "distinct_syscalls", "tag_entropy_bits",
                    "max_entropy_bits", "value_recurrence")},
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nNICHE VERDICT: {verdict}")
    print(reason)
    print(f"\n{'variant':>12} {'med':>8} {'min':>8} {'max':>8}")
    for k in ("bl_switch", "bl_memo", "eng_plan", "eng_jit", "eng_jit_nm"):
        v = st[k]
        print(f"{k:>12} {v['med']:>8.2f} {v['min']:>8.2f} {v['max']:>8.2f}")
    print(f"\nstream: {stream['events']} events, "
          f"{stream['distinct_syscalls']} kinds, "
          f"entropy {stream['tag_entropy_bits']}/"
          f"{stream['max_entropy_bits']} bits, "
          f"recurrence {stream['value_recurrence']:.1%}")


if __name__ == "__main__":
    main()
