#!/usr/bin/env bash
# One-command independent reproduction of every LAWFUL measurement on
# this branch. Intended for any Linux box with gcc + python3 (WSL
# works). Runs lawcheck first and refuses if any gate fails (Law 0),
# then the differential (correctness), then every engagement, printing
# each coded verdict. Writes nothing outside engine/results/ and a
# temp dir. ~10-20 minutes, most of it cc paving thousands of roads.
#
#   ./reproduce.sh
#
# Claim 1 (the dispatch-mechanism study, no engine involved) has its
# own sweep: claims/claim-1-shape-entropy/run.sh (~minutes).
set -euo pipefail
cd "$(dirname "$0")"

./lawcheck.sh
make -C engine >/dev/null

TR=niche/syscall-telemetry/traces
if [ ! -d "$TR" ]; then
    echo "capturing real syscall traffic (strace of real programs)..."
    niche/syscall-telemetry/capture.sh >/dev/null 2>&1
fi

echo "=== differential (walker == paved, matrix on == off, order) ==="
D=$(mktemp -d); NMO_JIT_DIR=$D engine/harness/differential; rm -rf "$D"

summarize() { python3 -c "
import json, sys
r = json.load(sys.stdin)
if 'machine_account' not in r:          # engagements wrap one key deep
    r = r[next(iter(r))]
for name in ('machine_account', 'baseline_account'):
    if name in r: print(' ', name, '=', json.dumps(r[name]))
if 'verdict' in r: print('  VERDICT:', r['verdict'])
"; }

cd engine
for h in measure rematch circulate fanout richpayload; do
    echo "=== $h ==="
    D=$(mktemp -d)
    if [ "$h" = circulate ]; then
        NMO_JIT_DIR=$D ./harness/$h ../$TR 15 3 | summarize
    else
        NMO_JIT_DIR=$D ./harness/$h ../$TR 15 | summarize
    fi
    rm -rf "$D"
done
echo "=== residency (claim 4 via the fabric) ==="
./harness/residency.sh
echo
echo "All lawful harnesses ran under passing gates. Recorded verdicts"
echo "and their environments live in engine/results/ and the READMEs;"
echo "your numbers above are your machine's account of the same code."
