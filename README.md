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
```

Python 3.8+, stdlib only.
