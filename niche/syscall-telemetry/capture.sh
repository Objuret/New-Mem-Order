#!/usr/bin/env bash
# Capture real event streams: the system calls of real programs doing
# real work on this machine. This is the traffic; nothing about it is
# synthesized, shaped, or filtered.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p traces work
REPO=$(cd ../.. && pwd)

T() { strace -f -qq -o "traces/$1.txt" "${@:2}" >/dev/null 2>&1 || true; }

# a real compile (gcc + as + ld, multi-process)
T gcc gcc -O2 -c "$REPO/engine/engine.c" -o work/engine_traced.o

# a real python program (claim-1's verdict over its real results)
T python python3 "$REPO/claims/claim-1-shape-entropy/verdict.py" \
    "$REPO/claims/claim-1-shape-entropy/results/raw.jsonl" work/v.json

# real git work
T git git -C "$REPO" log --stat --no-color

# a real build system run
T make make -C "$REPO/engine" clean all

# real archive round-trip of the repo
T tar bash -c "tar czf work/repo.tgz -C '$REPO' --exclude=.git . \
    && tar xzf work/repo.tgz -C work"

# a real filesystem walk
T find find /usr/share -name '*.txt' -size +1k

# a real recursive grep over real headers (thousands of file opens)
T grep grep -rl uint64_t /usr/include

# a bigger real compile: every C file in the repo, plus tests
T gcc2 bash -c "gcc -O2 -c '$REPO/engine/engine.c' -o work/e2.o &&
    gcc -O2 -I'$REPO/engine' -c '$REPO/engine/tests/test_engine.c' \
        -o work/t2.o &&
    gcc -O2 -I'$REPO/engine' -c '$REPO/claims/claim-2-circulation/bench.c' \
        -o work/b2.o &&
    gcc -O2 -I'$REPO/engine' -c '$REPO/claims/claim-3-exits/bench.c' \
        -o work/b3.o"

# real hashing and compression of real bytes
T hash bash -c "find /usr/lib/python3.11 -name '*.py' -size +4k \
    -exec sha256sum {} + | sort | gzip > work/hashes.gz"

# a second real python program (json over megabytes of real results)
T python2 python3 -c "
import json
rows=[json.loads(l) for l in open('$REPO/claims/claim-1-shape-entropy/results/raw.jsonl')]
print(len(rows), sum(r['ns_per_elem'] for r in rows))"

wc -l traces/*.txt
