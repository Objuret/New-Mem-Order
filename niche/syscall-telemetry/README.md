# Niche head-to-head #1: syscall telemetry — LOSS

MACHINE.md kill-list: "the engine must win one niche on measured
advantage." Kill condition: "real-world recurrence and shape-entropy
too low for the routed and memoized layers to pay."

First engagement on real traffic. **The machine lost. This file
records it; nothing here argues with the verdict.**

## Protocol

- **Traffic: real.** `capture.sh` straces real programs doing real
  work on this machine (gcc compiles, python, git, make, tar, find,
  grep, sha256+gzip). `edge.py` converts once at the edge:
  tag = syscall kind, value = return value. 98,658 events, 65 kinds.
- **Computation: imposed, one definition.** `gen.py` emits per-kind
  enrichment kernels (~12 vocabulary ops: errno value-fork via SELECT,
  size bucket, kind-specific mix) BOTH as engine arrangements and as
  inline C handlers — parity by construction, checked at runtime,
  abort on mismatch.
- **Five variants:** idiomatic switch; switch + direct-mapped memo
  (same geometry as the engine's — the strongest baseline, so the
  machine cannot win by a technique the opponent was denied); engine
  plan+memo; engine jit+memo (the full machine); engine jit no-memo.
- 9 interleaved steady-state reps after warmup; cold pass (including
  all paving) reported separately, never averaged in.

## Result (run of 2026-07-11, this commit)

**Coded verdict: LOSS** — `results/verdict.json` is authoritative.

| variant | med ns/event | range |
|---|---|---|
| bl_switch | **3.61** | 3.53–4.79 |
| bl_memo | 3.62 | 3.32–5.44 |
| eng_plan | 10.27 | 9.83–11.93 |
| eng_jit (the machine) | 10.07 | 9.42–11.86 |
| eng_jit_nm (no memo) | 9.61 | 9.23–10.57 |

Stream facts attached to the verdict: entropy 3.44 of 6.02 possible
bits (real syscall traffic is dominated by read/write/openat — ~11
effective kinds), value recurrence 94.5%.

## Operating point (a loss carries its operating point or nothing)

Kernels ~12 ops deep and fully inlineable; traffic entropy 3.4 bits;
single exit per event; single-threaded; virtualized host, wall-time
accounting.

## What the loss decomposes into (measured, in this run)

1. **The regime is the predictor's.** 3.4 bits of entropy is the
   skew-control side of claim 1's own map, where branchy dispatch
   was measured winning (claim 1 showed 1.73× branchy advantage under
   99% skew; the crossover needs entropy that this traffic does not
   have).
2. **v0 engine bookkeeping is the margin.** bl_switch does the whole
   job in ~3.6 ns. The engine's structural core can move batches of
   kernels this size at ~5 ns/event (claim 1's bare staging loop, same
   host); the engine runs ~9.6–10.3 — so roughly 4–6 ns/event of v0
   overhead: per-record feed/queue work and per-exit record
   construction + sink delivery. At kernel depth 12, there is nothing
   to amortize it against. (A first harness version charged another
   ~6 ns of its own sink division to the engine; fixed before this
   result — see git history.)
3. **The result matrix does not pay here** even at 94.5% recurrence:
   eng_jit_nm beats eng_jit. A random-access probe + per-element hit
   path costs more than batch-firing a 12-op kernel. Memoization is
   also not a moat: the baseline memoizes for free at 3.6 ns.
   Lookup-vs-compute only pays when compute is expensive; these
   kernels are not.

## What this does NOT license

Generalizing the loss. It is one operating point: shallow kernels ×
low-entropy traffic. Claim 2 (measured, PASS) says the machine's edge
grows with per-event depth; claim 1 (measured, PASS) says it grows
with shape entropy. Real niches at deeper work per event (parsers,
enrichment pipelines with real lookups, aggregation trees) and higher
kind-counts (real message buses speak hundreds of kinds) are where the
measured map says to aim next — and the next engagement must be as
honest as this one.
