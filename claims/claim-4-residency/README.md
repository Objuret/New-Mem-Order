# Claim 4 — Arrangement-residency fits

> **Law 0 reclassification (BUILD-LAW.md, merged after this run):**
> these numbers were produced by engine v0, which fails every gate
> (manager in the loop, batching with provenance metadata, computed
> identity, no fabric/edge separation). They are measurements of
> SCAFFOLDING composed with the machine's mechanisms — not results of
> the machine. They remain recorded as engineering data; the harness
> now runs `lawcheck` first and refuses to produce new numbers until
> the gates pass.


MACHINE.md, falsifiable claim 4:

> Resident bytes per shape; a ~1000-shape road network fits hot in L2
> where equivalent branchy code plus predictor state cannot.

## Protocol

The engine plants and paves 1024 shapes (8 mixed ops each, claim-1
scale) and accounts for its own road network: arrangements + paved
plans (`resident_network_bytes`), plus the engine's shared `.text`
(vocabulary + firing machinery), counted against it honestly. The
comparison object is the equivalent branchy dispatcher: the claim-1
generator's 1024 shapes inlined into one `switch`, compiled `-O2`,
the dispatcher function's code bytes read from the object file.

Coded conditions: FALSIFIED if the network doesn't fit L2; PASS only
if it fits AND is smaller than the branchy dispatcher's code alone;
INCONCLUSIVE if it fits but isn't smaller. The claim's "plus predictor
state" clause is hardware-internal and unmeasurable from software —
recorded as unmeasured, not scored.

## Result (run of 2026-07-11, this commit)

**Coded verdict: INCONCLUSIVE — and the reason is a real finding.**

| quantity | bytes |
|---|---|
| road network (1024 arrangements + plans) | 570,325 (~557/road) |
| engine shared .text | 9,173 |
| branchy dispatcher .text (bodies inlined) | 69,303 (~68/shape) |
| L2 on this host (4 instances) | 4 MiB |

The network fits L2 with room to spare (14%). But the v0 encoding is
**8× fatter than the branchy code it replaces**: 16-byte nodes and
16-byte plan steps, tree form retained after paving, and every
constant occupying a full node — while the compiler packs the same
op into ~8.5 bytes of instructions. "Arrangement is
information-theoretically tiny" is true in theory and NOT yet true of
this representation.

This is the engine's first measured deficiency and a concrete target:
pack plan steps, drop or page out the tree form after paving, inline
immediates. The claim stays open until the representation earns it —
or until a PMU host lets the predictor-state half be argued with
misprediction data instead of bytes.
