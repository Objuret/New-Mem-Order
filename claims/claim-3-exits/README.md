# Claim 3 — Exits-only collapses traffic

> **Law 0 reclassification (BUILD-LAW.md, merged after this run):**
> these numbers were produced by engine v0, which fails every gate
> (manager in the loop, batching with provenance metadata, computed
> identity, no fabric/edge separation). They are measurements of
> SCAFFOLDING composed with the machine's mechanisms — not results of
> the machine. They remain recorded as engineering data; the harness
> now runs `lawcheck` first and refuses to produce new numbers until
> the gates pass.


MACHINE.md, falsifiable claim 3:

> Bytes crossing the core/memory and node/node boundaries, staged vs
> circulating: ratio ~ intermediates over exits.

## Protocol

The same depth-D computation over 2M elements, two boundary
disciplines, both byte counts produced by code in the same run:

- **staged** — the conventional pipeline: each of the D operation
  stages materializes its full output array, and that array crosses
  the boundary to the next stage. Counted as written: D × M × 8 bytes.
- **exits-only** — the engine: circulation inside, only the single
  exit value crosses, through a naming channel (a value crosses once
  as `name+value` = 12 bytes; every recurrence crosses as a 4-byte
  name).

Parity enforced twice per run, abort on mismatch: the staged
pipeline's final array must equal the engine's exits element-for-
element, and the channel's decode side must reconstruct those values
exactly from the wire bytes.

Streams: unique-heavy (worst case for naming) and recurrent (1000
distinct values — where recurrence-as-reference should amplify).

Coded conditions: PASS requires measured ratio ≥ D/2 in every
configuration and recurrent > unique at equal depth; FALSIFIED if
exits-only ever moves more bytes than staging.

## Result (run of 2026-07-11, this commit)

**Coded verdict: PASS.**

| depth | stream | staged MB | exits MB | ratio |
|---|---|---|---|---|
| 4 | unique | 64.0 | 24.00 | 2.7× |
| 4 | recurrent | 64.0 | 8.01 | 8.0× |
| 16 | unique | 256.0 | 24.00 | 10.7× |
| 16 | recurrent | 256.0 | 8.01 | 32.0× |
| 64 | unique | 1024.0 | 24.00 | 42.7× |
| 64 | recurrent | 1024.0 | 8.01 | 127.9× |

Readings:

- On unique streams the measured ratio is exactly the predicted
  ⅔·D (8 bytes per intermediate vs 12 per named novel exit): traffic
  is proportional to what was CONCLUDED, and the constant of
  proportionality is the naming header.
- Recurrence multiplies it: with 1000 distinct values the wire is
  almost all 4-byte references — 128× at depth 64. Value travels once
  per novelty; recurrence travels as reference, measured.
- These are wire-format bytes counted by the channel itself, and the
  decode side reconstructs the exact values from exactly those bytes —
  the ratio cannot be an accounting fiction.
