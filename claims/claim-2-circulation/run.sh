#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# BUILD-LAW Law 0: this harness measures through the engine. It runs
# lawcheck first and REFUSES while any gate fails - a number produced
# under a failing gate would be scaffolding reported as the machine.
../../lawcheck.sh || { echo "lawcheck FAIL: Law 0 - harness refuses to measure." >&2; exit 1; }

M=${M:-2000000}
REPS=${REPS:-7}
mkdir -p results
make -C ../../engine libnmo.a >/dev/null
gcc -O2 -Wall -I../../engine bench.c ../../engine/libnmo.a -ldl -o bench

export NMO_JIT_DIR=$(mktemp -d)
: > results/raw.jsonl
for d in 4 8 16 32 64 120; do
    ./bench "$d" "$M" "$REPS" >> results/raw.jsonl \
        2>> results/paving.log
    echo "done depth=$d" >&2
done
rm -rf "$NMO_JIT_DIR"

{
    echo "kernel: $(uname -r)"
    echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2-)"
    echo "gcc: $(gcc --version | head -1)"
    echo "M=$M REPS=$REPS batch=256 memo=off"
    echo "virtualized: $(systemd-detect-virt 2>/dev/null || echo unknown)"
    echo "note: no PMU on this host - wall-time accounting only;"
    echo "the claim also names instructions and energy (unmeasured here)"
} > results/environment.txt

python3 verdict.py results/raw.jsonl results/verdict.json
