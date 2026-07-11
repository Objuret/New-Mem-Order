#!/usr/bin/env bash
# Claim 4 through the fabric: resident road-network bytes, measured
# from the real artifacts (no narrated bytes). Hot set = paved road
# code + road table + shared fabric text. Comparison = the same 688
# kernels as one compiled switch loop (bl_switch in baseline.so).
# The claim's "plus predictor state" clause remains unmeasurable from
# software and is recorded as unmeasured, not scored.
set -euo pipefail
cd "$(dirname "$0")/.."
../lawcheck.sh > /dev/null || { echo "Law 0: refuse" >&2; exit 1; }

DIR=$(mktemp -d)
export NMO_JIT_DIR=$DIR
./harness/rematch ../niche/syscall-telemetry/traces 3 > /dev/null

# switch-only branchy artifact: strip the memo variants from the
# baseline source, keep exactly the dispatch loop, compile alone
python3 - "$DIR" <<'PYEOF'
import re, subprocess, sys
d = sys.argv[1]
src = open(f"{d}/baseline.c").read()
cut = src.index("static inline uint64_t mx")
open(f"{d}/switch_only.c", "w").write(src[:cut])
subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-o",
                f"{d}/switch_only.so", f"{d}/switch_only.c"], check=True)
PYEOF

python3 - "$DIR" <<'EOF'
import json, re, subprocess, sys
d = sys.argv[1]

def text_bytes(obj):
    out = subprocess.run(["size", "-A", obj], capture_output=True,
                         text=True).stdout
    tot = 0
    for line in out.splitlines():
        p = line.split()
        if p and p[0].startswith(".text"):
            tot += int(p[1])
    return tot

def count_syms(so, pat):
    out = subprocess.run(["nm", "-S", so], capture_output=True,
                         text=True).stdout
    return sum(1 for l in out.splitlines()
               if len(l.split()) >= 4 and re.match(pat, l.split()[3]))

# whole-artifact .text on BOTH sides: every byte the job needs, no
# symbol-level guessing (inliner decisions do not skew the account)
roads = text_bytes(f"{d}/roads.so")
nroads = count_syms(f"{d}/roads.so", r"nmo_paved_\d+$")
blsw = text_bytes(f"{d}/switch_only.so")
fabric = text_bytes("fabric/fabric.o")
table = nroads * 16
machine = roads + table + fabric
l2 = 4 * 1024 * 1024
fits = machine <= l2
smaller = machine < blsw
verdict = ("FALSIFIED" if not fits
           else "PASS" if smaller else "INCONCLUSIVE")
res = {
    "claim": "4 via the fabric - arrangement-residency fits",
    "verdict": verdict,
    "unmeasured": "predictor/BTB state (the claim's 'cannot fit' half)",
    "paved_road_text_bytes": roads, "roads": nroads,
    "bytes_per_road": round(roads / nroads, 1),
    "road_table_bytes": table, "fabric_shared_text_bytes": fabric,
    "machine_resident_bytes": machine,
    "branchy_switch_loop_text_bytes": blsw,
    "l2_bytes": l2, "pct_of_L2": round(machine / l2 * 100, 1),
    "note": ("v1 note: the hot execution form is machine code on both "
             "sides now - v0's 8x arrangement-encoding fatness is gone; "
             "tree forms are retained only for the walker and can live "
             "cold"),
}
json.dump(res, open("results/residency_v1.json", "w"), indent=2)
print(f"CLAIM 4 (fabric) VERDICT: {verdict}")
print(f"machine {machine}B ({res['pct_of_L2']}% of L2, "
      f"{res['bytes_per_road']}B/road x {nroads}) "
      f"vs branchy switch loop {blsw}B")
EOF
rm -rf "$DIR"
