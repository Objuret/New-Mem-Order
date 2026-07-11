#!/usr/bin/env bash
# claim-1 sweep runner. Deterministic generation, fixed seeds.
# Primary:   L=8 ops/shape, uniform tags, N swept 2..1024, default -O2.
# Secondary: work-depth bounds (L=2, L=32) at N in {2,64,1024};
#            novec build (isolates predictability win from SIMD win);
#            skew control (low entropy at N=1024 - mechanism check).
set -euo pipefail
cd "$(dirname "$0")"

M=${M:-4000000}
REPS=${REPS:-7}
SEED=7
RAW=results/raw.jsonl
mkdir -p build results
: > "$RAW"

build_and_run() { # N L dist cflags_label extra_cflags
    local n=$1 l=$2 dist=$3 blabel=$4 extra=$5
    local dir="build/n${n}_l${l}_${blabel}"
    mkdir -p "$dir"
    if [ ! -f "$dir/sweep" ]; then
        python3 gen_shapes.py "$n" "$l" "$SEED" "$dir/shapes.h"
        gcc -O2 $extra -I"$dir" sweep.c -o "$dir/sweep"
    fi
    "$dir/sweep" "$M" "$REPS" "$dist" "$blabel" >> "$RAW"
    echo "done: N=$n L=$l dist=$dist build=$blabel" >&2
}

# primary sweep
for n in 2 4 8 16 32 64 128 256 512 1024; do
    build_and_run "$n" 8 uniform o2 ""
done

# novec: same sweep points, vectorization disabled everywhere
for n in 2 4 8 16 32 64 128 256 512 1024; do
    build_and_run "$n" 8 uniform novec "-fno-tree-vectorize"
done

# work-depth bounds
for n in 2 64 1024; do
    build_and_run "$n" 2  uniform o2 ""
    build_and_run "$n" 32 uniform o2 ""
done

# low-entropy control (mechanism check): 1024 declared shapes, 99% one tag
build_and_run 1024 8 skew o2 ""

{
    echo "kernel: $(uname -r)"
    echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2-)"
    echo "gcc: $(gcc --version | head -1)"
    echo "M=$M REPS=$REPS SEED=$SEED BLOCK=65536"
    echo "flags primary: -O2 ; novec: -O2 -fno-tree-vectorize"
    echo "virtualized: $(systemd-detect-virt 2>/dev/null || echo unknown)"
} > results/environment.txt

python3 verdict.py "$RAW" results/verdict.json
