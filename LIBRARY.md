# Structure Library Log

The running log required by build-brief step 2: every structure, why the
workload forced it, when. This is the primary experimental output of the
project. The library started empty; entries appear here in the order the
message-board workload forced them. `am/structures.py` and this file must
not drift.

## Library structures

| ID | Structure | Kind | Forced by | Date |
|----|-----------|------|-----------|------|
| 1 | `concat` | pure | Rendering a thread: a message must join the output of its chain (the demanded previous message) with its own fields. Also the only way to put two terminal emits inside one indivisible firing (see FRICTION.md #3). | 2026-07-08 |
| 2 | `emit-disk` | **TERMINAL** | Posting: a message must come to rest in the world as an unsent instruction file, and the thread-head reference file must be replaced to name it. The only structure with side effects. Binds to the single router (spec §2, Terminal structure). | 2026-07-08 |
| 3 | `select` | pure | Phase-2 query (a), find posts containing a value: filter-shaped computation `concat` cannot absorb. Keeps the segments of a value that contain a needle; the delimiter and needle are both comparison operands (values), so the record convention stays in the world, not the library. | 2026-07-08 |
| 4 | `tally` | pure | Phase-2 query (b), count posts per user: fold-shaped counting. Counts segments containing a needle; emits the count as decimal ASCII (the library's one number convention — FRICTION.md #11). Condition is a value. | 2026-07-08 |
| 5 | `last` | pure | Phase-2 query (c), N newest posts: positional selection. Returns the last N segments; N enters as a decimal-ASCII value. | 2026-07-08 |

## Grammar nodes used

Counted alongside library structures per spec §6 — relocating capability
into the grammar must not shrink the headline number.

| Node | Used for |
|------|----------|
| literal | every value: message text, users, timestamps, references-as-values, instruction-bytes-as-values |
| composition | every structure invocation |
| demand | reading = running: firing the head file, firing the message chain, persistence |
| error | refusals: missing reference, cyclic demand, malformed/truncated bytes, wrong arity |

## Headline §6 count — growth curve

| after | library structures | grammar nodes | total |
|---|---|---|---|
| phase 1 (message board) | 2 (1 pure + 1 terminal) | 4 | 6 |
| phase 2 (computation pressure) | 5 (4 pure + 1 terminal) | 4 | **9** |

Phase 2 grew the library by exactly the three query shapes (filter, fold,
positional take), all pure, all with conditions as values. The ~10
falsification threshold was not crossed. No grammar node was added.

## Structures considered and NOT added

- `socket-send` (terminal): the brief lists it as an expected terminal, but
  the workload never forced it — returning output to the demander is the
  demand return path (router mechanics, spec §2 Output), not a structure.
- `read-file`: forbidden by brief step 4; demanding covers it.
- `seq`: sequencing two emits was covered by `concat`; adding a
  dedicated sequencer was not forced (noted as friction instead).
- any constructor of instruction bytes from values (`make-demand-node`):
  would close the post race (FRICTION.md #2) but edges toward computed
  demand references; ruled to stay open by design (DECISIONS.md §2.1).
- `group-by` / key-extraction (phase 2): "count posts per user" for an
  UNKNOWN user set would need a structure that extracts keys between
  format markers — a resident parser. Refused; the demander supplies the
  user set instead (FRICTION.md #10).
- `count-lines`: `tally` with the needle every segment contains would
  cover it; never separately forced.
