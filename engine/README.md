# The engine

The component MACHINE.md closes with: the whole-stack agreement at the
silicon boundary, as an embeddable C runtime (OPTIONS.md decision 2a).
`nmo.h` is the entire public surface; `engine.c` is the machine.

## Layer map

| MACHINE.md | here |
|---|---|
| L1 roads — pre-staged straight-line plans; novel shapes paved on first arrival | `pave()`: linearize with register liveness; optionally `pave_jit()`: the plan becomes real machine code via `cc` + `dlopen`, once, at first arrival |
| L2 tags — data announces its road | `nmo_feed()`: the tag IS the index into the road table; routing never inspects payloads. Value-forks exist only as `NMO_OP_SELECT` inside arrangements — honest, small, kept |
| L3 residency & arrangement | the vocabulary is compiled in (installed once); a road adds only arrangement — nodes and plan steps. Staging queues live with the road: the cache stores the queue |
| L4 circulation — the program leaves the loop | `fire_road()`: the whole plan fires over a staged batch; intermediates live in the road's register file (or CPU registers on jit roads), die at slot reuse, and are unaddressable outside by construction |
| L5 exits — only exits are sent | exit nodes only leave a firing; per-road result matrix (grown by occurrence, direct-mapped) turns recurrence into lookup; `nmo_channel` turns recurrence into 4-byte names on the wire |

The four promises: records are immutable by-value; a value carries its
identity (v0: the u64 itself); recurrence becomes visible through the
result matrix and naming; arrangements are explicit, validated,
finite topology — mappable.

The safety condition is `validate()`: data can only ARRANGE the fixed
16-op vocabulary. Out-of-vocabulary ops, forward references, oversized
trees, and re-planting are rejected at the door. The jit path
generates code only from validated arrangements — immediates become
operands, never instructions. There is no eval anywhere.

## Using it

```c
nmo_config cfg = { .max_tags = 1024, .batch = 256,
                   .memo_entries = 4096, .jit = 1, .sink = my_sink };
nmo_engine *e = nmo_create(&cfg);
nmo_plant(e, &arrangement);        /* validated; tree installed      */
nmo_feed(e, records, n);           /* routed, staged, fired; exits
                                      arrive at the sink             */
nmo_drain(e);                      /* flush partial batches          */
```

`make test` runs the differential suite: walker, plan, and jit paths
must be bit-identical on random arrangements and streams, with and
without the result matrix; plus safety rejections, channel round-trip
with exact byte accounting, and the liveness bound.

## Honest state (v0)

- Single-threaded; u64 payloads; one input slot per record.
- Batching trades per-element latency for throughput; exits are not
  in arrival order across tags (they carry `src` sequence numbers).
- The result matrix is direct-mapped (cache semantics): recurrence is
  found probabilistically, never invented — a collision only ever
  costs a recompute.
- Measured deficiency (claim 4): the v0 arrangement/plan encoding is
  ~8× fatter per op than compiled branchy code. Packing steps and
  paging out tree forms after paving is the named target.
- Claim measurements through this engine: claim 2 PASS, claim 3 PASS,
  claim 4 INCONCLUSIVE (see `claims/`).
