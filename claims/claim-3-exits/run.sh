#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

M=${M:-2000000}
mkdir -p results
make -C ../../engine libnmo.a >/dev/null
gcc -O2 -Wall -I../../engine bench.c ../../engine/libnmo.a -ldl -o bench

: > results/raw.jsonl
for d in 4 16 64; do
    for dist in unique recurrent; do
        ./bench "$d" "$M" "$dist" >> results/raw.jsonl
        echo "done depth=$d dist=$dist" >&2
    done
done

{
    echo "kernel: $(uname -r)"
    echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2-)"
    echo "M=$M batch=256 memo=off"
    echo "byte counters are code-side on both sides; channel decode"
    echo "parity enforced in-bench (abort on mismatch)"
} > results/environment.txt

python3 verdict.py results/raw.jsonl results/verdict.json
