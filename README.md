# The Activation Model — Falsification Prototype

Read `activation-model.md` (the spec — authoritative) and `build-brief.md`
(what to build, what counts as done) first. This repo is the prototype the
brief describes: a minimal runtime for the four axioms plus a message
board built on it, to measure how many structures real work actually
needs (spec §6).

## Layout

| path | what |
|---|---|
| `am/instruction.py` | the grammar: one encoder, byte-walking `fire()` — the only form anything has |
| `am/structures.py` | the library (5 universal structures; log in `LIBRARY.md`) |
| `am/router.py` | one event loop: receive → resolve → fire whole → return |
| `am/client.py` | the world side: builds instructions, displays outputs |
| `am/layer.py` / `am/fuse.py` | phase 3: the FUSE layer — files as chains, reading fires |
| `am/condense.py` | phase 3: offline condensation pass (promotes recurring content) |
| `demo.py` / `report.py` / `phase3_tests.py` | end-to-end runs and measurements |
| `LIBRARY.md` | structure log — primary experimental output |
| `FRICTION.md` | where the model fought back |
| `DECISIONS.md` | judgment calls + open questions for Jocke |
| `REPORT.md` | the four measurements and the §6 verdict |

## Run it

```
python3 demo.py      # two users post & read through the router; restart survival
python3 report.py    # measurements from the run

# or by hand:
python3 -m am.router &          # world/ is created next to it
python3 -m am.client new-thread general
python3 -m am.client post general alice "hello"
python3 -m am.client read general
python3 -m am.client find general "hello"     # posts containing a value
python3 -m am.client count general alice bob  # posts per (named) user
python3 -m am.client newest general 2         # N newest posts

# phase 3 — the layer (needs FUSE; see PHASE3-STATE.md for env recipe):
python3 phase3_tests.py                       # all four acceptance tests
python3 -m am.fuse MOUNTPOINT --store store   # mount by hand
python3 -m am.condense --store store          # offline condensation pass

# phase 4 — computation + shape condensation:
python3 phase4.py                             # ledger workload, queries,
                                              # shape pass, idempotency
python3 -m am.shapemine --world world         # shape pass by hand

# phase 5 — the wire (run phase4.py first):
python3 phase5.py                             # two routers: replication,
                                              # dictionary bootstrap, deltas

# phase 6 — compaction + render cache (run phase3_tests.py first):
python3 phase6.py                             # reclaim history, price cache
python3 -m am.compact --store phase3/store    # compaction by hand

# phase 7 — multi-writer, merge-as-query:
python3 phase7.py                             # two writers, convergence

# phase 8 — open-key grouping via write-side projection:
python3 phase8.py                             # unknown users discovered

# phase 9 — scale: 11 MB of real stdlib source, full pipeline:
python3 phase9.py

# phase 10 — snapshot corpus: dedup vs gzip rematch:
python3 phase10.py

# phase 11 — native fire loop (C), speed vs cat:
python3 phase11.py                            # builds native/amfire.c

# phase 13 — THE metric: same job, both stacks, crossings per byte:
python3 phase13.py

# phase 14 — amd: the native router, gated + true benchmarks:
python3 phase14.py                            # builds native/amd.c

# phase 15 — a program: branching + sequential state, zero new structures:
python3 phase15.py

# phase 16 — the memory path: bytes, cache misses, time (needs valgrind):
python3 phase16.py                            # builds native/membench.c

# phase 17 — amx: the mmap'd-pack engine, offset references (DECISIONS 2.4):
python3 phase17.py                            # builds native/amx.c

# on YOUR machine — the memory-path experiment with real CPU counters:
#   any box with a C compiler + python3; perf/simpleperf + RAPL if present
#   Android: install Termux (F-Droid), then: pkg install python clang git
python3 hwbench.py

# phase 12 — am.tool, the snapshot/replication CLI:
python3 phase12.py                            # full workflow end to end
python3 -m am.tool snap DIR --label v1        # then: snaps, ls, cat,
python3 -m am.tool restore v1 OUT             # restore, verify, stats,
python3 -m am.tool push HOST:PORT             # serve, push, mount
```

Python 3.8+, stdlib only. FUSE phases need `fusepy`, which does NOT
pip-install cleanly on recent Ubuntu — see PHASE3-STATE.md for the
hand-install recipe; without it the five FUSE-dependent harnesses skip.

`robustness_tests.py` pins hostile-input behavior (NUL references, deep
nesting, garbage, traversal, corrupt heads → refusals/EIO, never a crash).

`CRITICAL-REVIEW.md` (branch `claude/critical-build-review-42kzhx`) is an
external adversarial audit; `RESPONSE-TO-REVIEW.md` and the ERRATA section
at the top of REPORT.md are its answer — read those before quoting any
headline number from this repo.
