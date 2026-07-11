#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# BUILD-LAW Law 0: this harness measures through the engine. It runs
# lawcheck first and REFUSES while any gate fails - a number produced
# under a failing gate would be scaffolding reported as the machine.
../../lawcheck.sh || { echo "lawcheck FAIL: Law 0 - harness refuses to measure." >&2; exit 1; }

mkdir -p results build
make -C ../../engine libnmo.a >/dev/null
gcc -O2 -Wall -I../../engine bench.c ../../engine/libnmo.a -ldl -o bench

# the engine's road network, self-accounted
./bench 1024 8 > results/engine.json

# the equivalent branchy dispatcher: claim 1's 1024 shapes inlined into
# one switch, compiled -O2; only the dispatcher's own code is counted
python3 ../claim-1-shape-entropy/gen_shapes.py 1024 8 7 build/shapes.h
cat > build/branchy.c <<'EOF'
#include <stdint.h>
typedef struct { uint64_t val; uint32_t idx; uint32_t pad; } rec_t;
#include "shapes.h"
uint64_t branchy_dispatch(uint32_t tag, uint64_t x) {
    return dispatch_switch(tag, x);
}
EOF
gcc -O2 -ffunction-sections -c build/branchy.c -o build/branchy.o
BRANCHY_TEXT=$((16#$(nm -S build/branchy.o \
    | awk '$NF == "branchy_dispatch" {print $2; exit}')))

# the engine's own machinery (vocabulary + firing kernels), shared by
# every road - counted against the engine, honestly
ENGINE_TEXT=$(size -A ../../engine/engine.o | awk '$1==".text" {print $2}')

L2_BYTES=$(lscpu -B 2>/dev/null | grep -m1 'L2' | cut -d: -f2 \
    | grep -o '[0-9]\+' | head -1 || true)
[ -n "$L2_BYTES" ] && [ "$L2_BYTES" -gt 0 ] || L2_BYTES=$((4*1024*1024))

{
    echo "kernel: $(uname -r)"
    echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2-)"
    echo "L2 (all instances): $L2_BYTES bytes"
    echo "branchy .text (dispatcher fn, bodies inlined): $BRANCHY_TEXT"
    echo "engine .text (vocabulary + machinery, shared): $ENGINE_TEXT"
} > results/environment.txt

python3 verdict.py results/engine.json "$BRANCHY_TEXT" "$ENGINE_TEXT" \
    "$L2_BYTES" results/verdict.json
