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

## Grammar nodes used

Counted alongside library structures per spec §6 — relocating capability
into the grammar must not shrink the headline number.

| Node | Used for |
|------|----------|
| literal | every value: message text, users, timestamps, references-as-values, instruction-bytes-as-values |
| composition | every structure invocation |
| demand | reading = running: firing the head file, firing the message chain, persistence |
| error | refusals: missing reference, cyclic demand, malformed/truncated bytes, wrong arity |

## Headline §6 count

**2 library structures (1 pure + 1 terminal) + 4 grammar nodes = 6.**

## Structures considered and NOT added

- `socket-send` (terminal): the brief lists it as an expected terminal, but
  the workload never forced it — returning output to the demander is the
  demand return path (router mechanics, spec §2 Output), not a structure.
- `read-file`: forbidden by brief step 4; demanding covers it.
- `seq` / `last`: sequencing two emits was covered by `concat`; adding a
  dedicated sequencer was not forced (noted as friction instead).
- any constructor of instruction bytes from values (`make-demand-node`):
  would close the post race (FRICTION.md #2) but edges toward computed
  demand references; left for Jocke — see DECISIONS.md.
