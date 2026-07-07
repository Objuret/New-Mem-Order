# New Mem Order — Activation Model Prototype

A falsification prototype for the activation model: a runtime with no data
layer, no parsing, no serialization, no locks, and no store — only a fixed
set of resident structures and instructions in flight.

- **`activation-model.md`** — the spec. Authoritative, untouched.
- **`build-brief.md`** — what to build and what counts as done.
- **`report.md`** — the run-2 results, including the §6 structure count: **3**.
- **`structure-log.md`** — why each structure exists, and what was removed (primary experimental output).
- **`friction-log.md`** — every place the model fought back, and the verdict.
- **`spec-amendments.md`** — three proposed spec lines from the run-1 review, awaiting Jocke.

## Layout

| file | role |
|---|---|
| `instruction.py` | The one representation: encoder + grammar walkers. File format = wire format = execution format. Grammar nodes: value, fire, demand (fire the stored instruction a reference names), error (the reserved form for a refused firing). |
| `structures.py` | The fixed structure library (3 entries, grown from empty on demand — nothing in it can fire bytes) and the firing walk. Firing interprets the bytes directly — there is no decoded tree anywhere. |
| `router.py` | One event loop: receive instruction → resolve IDs → fire whole → return output to the demander. No locks, no queues. |
| `client.py` | The message-board workload, expressed purely as instruction compositions. Also a CLI. |
| `demo.py` | Harness (not the model): two clients, router restart, the four measurements. |

## Run it

```sh
python3 demo.py                       # full demo + measurements (uses ./data)

# or by hand:
python3 router.py 7801 ./data &
python3 client.py 7801 init
python3 client.py 7801 create general
python3 client.py 7801 post general 2026-07-07T10:00:00Z alice "hello board"
python3 client.py 7801 read general
python3 client.py 7801 threads
```

Stdlib only, Python ≥ 3.9. Persistence is nothing but the files under
`./data/board/` — each one is an unsent instruction; restart the router and
demand them again.
