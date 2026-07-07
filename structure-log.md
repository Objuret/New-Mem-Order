# Structure Log

The primary experimental output (build brief, step 2). The library started
empty; every entry below records a structure the workload *forced*, why, and
when. Terminals are marked — they are the only structures allowed side
effects (brief, step 4).

| ID | Name | Terminal | Added | Forced by |
|---|---|---|---|---|
| 1 | `concat` | no | 2026-07-07 | Posting appends a message line to existing thread content; also doubles as the sequencing combinator (args evaluate in order), which "create thread" uses to do its two writes as one tree. |
| 2 | `quote` | no | 2026-07-07 | Persistence-as-files requires producing an *instruction* as output: the new thread file must be bytes that fire to the thread content. `quote` wraps evaluated bytes as a literal-value instruction. Without it, outputs are content, never demandable instructions. |
| 3 | `eval` | no | 2026-07-07 | Demanding a stored reference means firing the bytes read from it. `eval` is the demand verb: fire these bytes as an instruction. Reading a thread is `eval(read-file(ref))` — reading IS running (spec §3). |
| 4 | `read-file` | **yes** | 2026-07-07 | The reference→unsent-instruction edge. Demanding anything persistent starts here. Brief step 4's "read-fd as demand". |
| 5 | `write-file` | **yes** | 2026-07-07 | The only way state survives restart: emit an unsent instruction to disk at a reference. Brief step 4's emit-to-disk terminal. Returns the reference, so the output is demandable onward. |

**Total: 5.** Nothing else was needed. Structures considered and *rejected*
because the workload never forced them:

- `list-directory` — would have been a lookup subsystem in disguise. The
  thread index is itself just a thread (`index`), maintained by the same
  post composition. The spec's "the demander holds the reference" held.
- any conditional / `read-or-default` — wanted once, at first contact with
  a missing index. Resolved by making board establishment an explicit
  bootstrap instruction instead (friction log #2).
- `socket-send` terminal — the demand's return path already covers the
  workload's networking; the router returns output to the demander's
  connection. No instruction ever needed to push to a *different* wire.
