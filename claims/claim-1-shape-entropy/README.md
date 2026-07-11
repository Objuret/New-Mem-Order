# Claim 1 — Routing beats prediction where shape-entropy is high

MACHINE.md, falsifiable claim 1:

> Tag-routed dispatch vs branchy dispatch over the same stream, swept
> from 2 to ~1000 interleaved shapes: crossover as predictor tables
> thrash, widening without bound. (The one prior test of shape-compiled
> firing ran at 2-3 shapes — where predictors are perfect — and lost;
> the claimed regime has never been measured.)

This directory is the first measured apparatus of the machine. Its
routed side is built from MACHINE.md's own parts: shapes are
arrangements of a fixed op vocabulary (layer 3), each shape has a
pre-staged straight-line firing plan (layer 1), data arrives tagged
(layer 2), and the cache holds per-road queues that fire as units
(layers 3/4).

## Protocol

A stream of M=4,000,000 `(tag, value)` pairs, tags uniform-random over
N shapes (maximum shape-entropy for that N), N swept over
2..1024. Every shape is a distinct straight-line sequence of L ops
drawn from a fixed 6-op vocabulary (add/xor/mul-const, rotate,
xor-shift, add-shift on u64), deterministically generated from a fixed
seed. Every variant computes the identical result array; checksums are
compared at startup and the run **aborts on any mismatch** (guarantee
parity is enforced, not assumed).

Four dispatch mechanisms over the same stream:

| variant | what it is |
|---|---|
| `branchy_switch` | dense `switch` inlined into the loop (gcc emits a jump table: one indirect branch per element). The strong conventional baseline. |
| `branchy_chain` | binary comparison tree over the tag (~log2 N conditional branches per element) — the sparse-dispatch idiom. |
| `routed_direct` | per-element hop through the road table (`SHAPE_FN[tag]`). The **naive** reading of tag-routing; reported as a diagnostic. |
| `routed_staged` | the machine's reading: per 64K-element block, partition records by tag into per-road queues (count/prefix/scatter — indexed ops, no data-dependent branches), then each road's firing plan runs over its whole batch straight-line. Results land at original stream indices. |

The claim is judged **routed_staged vs the stronger of the two branchy
baselines at each N** — it must beat the strongest conventional
opponent, not a strawman.

7 repetitions per configuration, interleaved round-robin after an
untimed warmup; medians and min–max ranges reported. Process pinned to
one CPU.

### Falsification conditions (coded in `verdict.py`, not narrated)

- `beat(N)`: routed_staged's **max** < branchy_best's **min** (ranges
  must not overlap).
- **PASS**: a crossover N\* exists, `beat(N)` holds for every measured
  N ≥ N\*, and the advantage ratio at N=1024 exceeds the ratio at N\*
  (widening).
- **FALSIFIED**: branchy_best's max < routed_staged's min at N=1024 —
  routing decisively loses even at the highest entropy measured.
- **INCONCLUSIVE**: anything else.

### Controls and secondary accountings

- **Low-entropy control** (mechanism check): N=1024 declared shapes but
  99% of traffic on one tag. The predictor must recover — if
  branchy_switch is not fast again here, the attribution of its
  high-entropy slowdown to predictor thrash is wrong.
- **Work-depth bounds**: primary L=8 ops/shape; L=2 and L=32 measured
  at N ∈ {2, 64, 1024} so the operating point is bounded, not
  cherry-picked.
- **novec build** (`-fno-tree-vectorize`): straight-line firing plans
  are auto-vectorizable and branchy interleave is not — that advantage
  is real but must be reported separately from the predictability win.
- Deterministic streams and shape generation (fixed seeds); rerunning
  `./run.sh` reproduces the workload bit-for-bit.

### Known limitations of this run (stated, per claim discipline)

- Virtualized 4-vCPU cloud Xeon; **no PMU exposed**, so branch-miss and
  instruction counts are unavailable here and the accounting is
  wall-time only. The harness reads the counters automatically when a
  PMU exists; rerun on bare metal to add that accounting.
- `routed_staged` trades per-element latency for throughput (results
  are correct and complete per 64K block, but not produced in arrival
  order). Same-stream-order latency is not what claim 1 claims, but it
  is the honest cost of staging.
- Uniform tags are the maximum-entropy point for a given N; real
  streams sit between the skew control and this.

## How to run

```
./run.sh          # full sweep, ~minutes; writes results/
M=1000000 REPS=3 ./run.sh   # quicker, noisier
```

Outputs: `results/raw.jsonl` (every measurement), `results/verdict.json`
(coded verdict + tables), `results/environment.txt` (operating point).

## Result

See `results/verdict.json` (generated, coded verdict — this README does
not overrule it). Summary of the run recorded in this commit: see the
table and verdict in that file.
