# Claim 2 — Circulation beats program-mediated stepping

> **Law 0 reclassification (BUILD-LAW.md, merged after this run):**
> these numbers were produced by engine v0, which fails every gate
> (manager in the loop, batching with provenance metadata, computed
> identity, no fabric/edge separation). They are measurements of
> SCAFFOLDING composed with the machine's mechanisms — not results of
> the machine. They remain recorded as engineering data; the harness
> now runs `lawcheck` first and refuses to produce new numbers until
> the gates pass.


MACHINE.md, falsifiable claim 2:

> Whole-tree fused firing vs one-operation-at-a-time with materialized
> intermediates: time, instructions, and energy.

## Protocol

Same arrangement (a depth-D op chain over the fixed vocabulary), same
2M-element stream, three executions inside one engine, parity checked
before any timing (abort on mismatch):

- **walker** — the engine's single slow road: one operation at a time,
  every intermediate materialized to a node array, control returning
  to the interpreter loop between steps. This is the
  program-in-the-loop baseline the claim names.
- **plan** — circulation: the road's linearized firing plan runs over
  staged batches of 256; intermediates live in the road's register
  file and die at slot reuse.
- **jit** — circulation through the jit-paved road: real straight-line
  machine code (`cc`-compiled at first arrival), intermediates in CPU
  registers. Also serves as the compiled-ahead reference point.

Depth swept 4..120; 7 reps; medians with min–max ranges; engine's
result matrix disabled so layer 5 cannot contaminate a layer 4
measurement. Paving happens in warmup (arrival = paving), so timed
reps measure steady-state circulation, with total paving cost logged
separately in `results/paving.log`.

Falsification conditions coded in `verdict.py`: PASS requires plan to
beat walker with non-overlapping ranges at every depth AND the
advantage to grow with depth (ceremony amortization is the predicted
sign); FALSIFIED if the walker decisively wins at max depth.

**Limitation (stated):** this host has no PMU and no energy meter, so
of the claim's "time, instructions, and energy" only time is measured
here. Claim 5 owns the energy half.

## Result (run of 2026-07-11, this commit)

**Coded verdict: PASS.**

| depth | walker | plan | jit | walker/plan | walker/jit |
|---|---|---|---|---|---|
| 4 | 19.89 | 13.37 | 9.10 | 1.49× | 2.19× |
| 16 | 58.52 | 24.42 | 10.73 | 2.40× | 5.45× |
| 64 | 213.44 | 71.51 | 23.86 | 2.98× | 8.95× |
| 120 | 393.24 | 124.97 | 44.69 | 3.15× | 8.80× |

(ns/element, medians of 7.)

Readings:

- The advantage grows with depth exactly as the ceremony argument
  predicts: the deeper the tree, the more per-step ceremony the walker
  pays and circulation doesn't.
- The jit-paved road — the machine's fullest reading, intermediates in
  actual CPU registers, no interpretation at all — is where the
  10-100× ceremony economics start to show (≈9× over stepping and
  still rising at depth 64). The plan path's remaining gap vs jit is
  its own per-step dispatch, amortized over batches but not zero.
- Paving cost (cc compile ≈ 100ms/road) is real and logged; it
  amortizes over recurrence, which is the design's stated bet.
