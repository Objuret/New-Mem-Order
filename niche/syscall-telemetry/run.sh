#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# BUILD-LAW Law 0: this harness measures through the engine. It runs
# lawcheck first and REFUSES while any gate fails - a number produced
# under a failing gate would be scaffolding reported as the machine.
../../lawcheck.sh || { echo "lawcheck FAIL: Law 0 - harness refuses to measure." >&2; exit 1; }
# RETIRED: this harness drives the v0 scaffolding API (engine/scaffold-v0).
# Its recorded results stand as scaffolding data; new numbers require the
# fabric port. Refusing unconditionally so a gate-passing tree cannot
# accidentally produce fresh v0 numbers.
echo "retired: v0 scaffolding harness; fabric port pending" >&2; exit 1

REPS=${REPS:-9}
mkdir -p results
make -C ../../engine libnmo.a >/dev/null

# capture only if no stream exists (results stay tied to one stream);
# the committed records.bin.gz is the exact stream of the recorded run
if [ ! -f records.bin ]; then
    if [ -f records.bin.gz ]; then
        gunzip -k records.bin.gz
    else
        ./capture.sh
        python3 edge.py records.bin stream_stats.json
    fi
fi

python3 gen.py stream_stats.json shapes.h
gcc -O2 -Wall -I../../engine -I. bench.c ../../engine/libnmo.a -ldl -o bench

export NMO_JIT_DIR=$(mktemp -d)
./bench records.bin "$REPS" > results/raw.jsonl 2> results/engine_stats.txt
rm -rf "$NMO_JIT_DIR"

{
    echo "kernel: $(uname -r)"
    echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2-)"
    echo "gcc: $(gcc --version | head -1)"
    echo "REPS=$REPS batch=256 memo=4096/road (engine and baseline)"
    echo "virtualized: $(systemd-detect-virt 2>/dev/null || echo unknown)"
    echo "traffic: real strace of real programs (see capture.sh);"
    echo "kernels: imposed enrichment (gen.py), same definition both sides"
} > results/environment.txt
cp stream_stats.json results/

python3 verdict.py results/raw.jsonl stream_stats.json results/verdict.json
