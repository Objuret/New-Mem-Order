# Structure Log

The primary experimental output (build brief, step 2). The library started
empty; every entry records a structure the workload *forced*, why, and
when. Terminals are marked — they are the only structures allowed side
effects (brief, step 4).

## Current library — 3 structures

| ID | Name | Terminal | Added | Forced by |
|---|---|---|---|---|
| 1 | `concat` | no | 2026-07-07 | Posting appends a message line to existing thread content; also doubles as the sequencing combinator (args evaluate in order), which "create thread" uses to do its two writes as one tree. |
| 2 | `quote` | no | 2026-07-07 | Persistence-as-files requires producing an *instruction* as output: the new thread file must be bytes that fire to the thread content. `quote` wraps evaluated bytes as a literal-value instruction. Without it, outputs are content, never demandable instructions. |
| 3 | `write-file` | **yes** | 2026-07-07 | The only way state survives restart: emit an unsent instruction to disk at a reference. Brief step 4's emit-to-disk terminal. Returns the reference, so the output is demandable onward. |

None of these can fire bytes. Complexity cannot be smuggled through
values-in-flight without first becoming a stored, referenced, unsent
instruction — so the §6 failure branches stay measurable.

## Removed in run 2 (review finding — see friction-log.md #6)

| Name | Was ID | Removed | Why removed |
|---|---|---|---|
| `eval` | 3 | 2026-07-07 | Fire arbitrary in-flight bytes = a universal interpreter. With it resident, the §6 count freezes forever because any workload can push complexity into values — the review caught that this disabled the very measurement the prototype exists for. Empirically the workload never needed it: every `eval` in run 1 fired a stored *literal*, i.e. was really a demand. |
| `read-file` | 4 | 2026-07-07 | Subsumed: the workload never wanted a file's bytes without firing them. Demand-by-reference (read + fire, spec §3.1/A4) is core machinery and now lives in the instruction grammar as the `demand` node — see spec-amendments.md #1. |

Run-1 → run-2 renumbering: `write-file` 5→3. IDs are frozen *within* a
library generation; the generation changed because the review changed the
set, which is exactly the kind of event the log exists to record.

## Considered and rejected (never entered the library)

- `list-directory` — would have been a lookup subsystem in disguise. The
  thread index is itself just a thread (`index`), maintained by the same
  post composition. The spec's "the demander holds the reference" held.
- any conditional / `read-or-default` — wanted once, at first contact with
  a missing index. Resolved by making board establishment an explicit
  bootstrap instruction instead (friction log #2).
- `socket-send` terminal — the demand's return path already covers the
  workload's networking; the router returns output to the demander's
  connection. No instruction ever needed to push to a *different* wire.
- `value-of` (unwrap a literal instruction without firing it) — the
  narrower alternative to killing `eval`; rejected in favor of the demand
  node because it would treat stored instructions as data to destructure,
  weakening "reading IS running" to bookkeeping.
