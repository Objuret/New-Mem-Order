# The engine, v1 — fabric and edge

Built under BUILD-LAW; `../lawcheck.sh` passes all six gates against
this tree. `scaffold-v0/` is the retired first build (Law 0 banners in
its harnesses' READMEs explain why its numbers are scaffolding data).

- `fabric/` — the machine: one arrive path (matrix consult by carried
  name, else one indirect dispatch into the road), the generic walker,
  road-to-road circulation. Two functions. Nothing else.
- `edge/` — every compromise, registered in `EMULATION.md`: planting,
  cc+dlopen paving, naming at birth, boundary channel, strace
  conversion with entropy printed before and after.
- `harness/` — differential (walker == paved, matrix on == off, order
  exact), measure (two ledgers), rematch (niche verdict, coded).

Recorded run (`results/`, 2026-07-11, virtualized Xeon, wall-time):
real strace traffic, shape-preserving edge: 98,733 events, 688 tags,
entropy 4.56 bits (v0's flattening edge saw 65 tags / 3.44 bits in the
same traffic). Machine 3.11 ns/event vs strongest conventional
baseline 4.83 (switch; hash-memoized switch 4.91) — **coded verdict:
WIN, ranges disjoint.** Ablation (edge + flat loop, no fabric): 2.22 —
the fabric's remaining ~0.9 ns overhead, named as the next target.
Emulation ledger: paving 5.9 s for 688 roads, convert ~0.7 µs/event
(text parsing; real deployments feed binary).

Circulation engagement (`results/circulate.json`, same stream, 3-stage
chains per event, 2064 trees): trees-feed-trees circulation 8.55
ns/event beats even the compiled-fused ceiling (10.84) and crushes the
materializing pipeline (14.40, which also crossed 1.58 MB of
intermediates vs the machine's 0). Full machine (whole-chain result
matrix under the entry name) 1.97 vs strongest conventional
(fused+hash-memo) 3.82 — **coded verdict: WIN, trimmed ranges
disjoint** (symmetric 1-rep trim, declared pre-verdict, both sides).

Depth sweep (`results/circulate_depth_verdict.json`, S = 1,2,4,8
stages per event): the full machine WINS at every depth (3.0-3.3
ns/event, essentially depth-flat) while every opponent scales with S
(pipeline 4.5→42.5, fused 4.7→34.6, fused+hash 4.6→5.9). The
pipeline-over-circulation ratio grows monotonically 0.78x→1.98x, and
pure circulation beats compiled fusion at every S ≥ 2 (at S=8: 21.4 vs
34.6). Composite coded verdict: INCONCLUSIVE — the pre-coded condition
required circulation to track fusion at S=1, where a chain has one
tree and no circulation exists; the condition misfires there and is
recorded as written, not rewritten after the fact. Every per-depth
machine verdict is WIN.

Residency, v1 accounting (`results/residency_v1.json`): whole-artifact
.text both sides, same 688 kernels. Machine resident = 99,809B
(127.8B/road paved code + road table + shared fabric text) = 2.4% of
L2; branchy switch-only loop = 52,209B. Coded verdict: INCONCLUSIVE —
fits L2 trivially but is ~1.9x the branchy bytes (per-road function
prologues and table-indirect call sequences vs one shared switch
loop). v0's 8x arrangement-encoding fatness is gone (the hot form is
machine code on both sides now); the remaining 1.9x is the next
residency target. Predictor-state half remains unmeasurable, recorded
as unmeasured.

Fan-out capability (this commit): trees may conclude in multiple
boundary exits; the result matrix generalizes to per-root strides
(replaying ALL of a chain's exits from one indexed block), with the
single-exit fast layout preserved when no fan-out roots exist (an A/B
showed the naive generalization cost ~0.7 ns on the flagship path;
the dual layout restored it to within ~0.1-0.2 ns). Differential now
covers fan-out (58,378 exits from 50k arrivals, walker==paved, order
exact). G1's counter now measures the dedicated dispatch primitive
(nmo_road_entry, 8 instructions) - the static count-to-first-call
proxy was conflating layer-5 replay code with dispatch.
`results/rematch_fanout_fabric.json` is the post-change rerun: means
still favor the machine (3.71 vs 4.27) but the VM's noise floor
widened intra-day and ranges overlap - INCONCLUSIVE as coded; the
recorded WIN stands tied to its own commit and environment. Rerun both
on quieter hardware to settle.
