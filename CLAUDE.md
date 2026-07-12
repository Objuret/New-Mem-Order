# THE MACHINE — Session Orientation (branch: machine)

## Read first, in order
1. `MACHINE.md` — the spec, the only source of truth on this branch.
   Derived from Jocke's own statements (2026-07-11); his quotes are the
   axioms, formalizations are subordinate and provisional.
2. `DERIVATION.md` — the reasoning chain that produced the spec, the
   five corrections Jocke had to issue on the way, and the settled
   arguments. Read it to RE-DERIVE the machine, not just obey it — an
   agent that can't re-derive it will reinterpret it into whatever it
   already knows, which is exactly the failure it documents.
3. `SOUL.md` — the conversation itself, both voices, preserved
   near-verbatim while it was whole in context. The primary source.
   Where SOUL, DERIVATION, and MACHINE disagree, that order wins:
   what Jocke actually said outranks every distillation of it.
4. `BUILD-LAW.md` — BINDING before any engine work. Twenty builds by
   two agents proved that documents 1-3 produce correct confessions,
   not correct builds: the builder's scaffolding replaces the machine
   under pressure, reliably, despite sincere intent. BUILD-LAW removes
   the builder's judgment from the loop: mechanical gates, checked by
   script, and Law 0 — no number is ever reported as the machine's
   while a gate fails. If you are about to write engine code and
   `lawcheck` does not exist yet, that is the first thing you build.

## The firewall (why this branch exists)
The prior prototype lives on `claude/build-it-r1yzg9` — 19 phases, a
measurement record, an external adversarial review, and corrections.
It is PRIOR ART, nothing more:

- Never import its vocabulary, code, file layout, or design choices by
  default. If something from it is genuinely needed, name it, say why,
  and ask.
- Its measurements may be CITED (they survived hostile review where
  noted there) but its architecture has no authority here. It
  implements at most 1.5 of MACHINE.md's five layers.
- Do not check it out, merge it, or copy from it without Jocke's
  explicit instruction.

## Working rules (learned the hard way, kept on purpose)
1. **Concept before construction.** When Jocke states an idea, restate
   it at concept level and get his confirmation BEFORE mapping it to
   any implementation. Never sort his thoughts into existing boxes;
   never dismiss a part because a past experiment "already covered it."
2. **Options first on structural silences.** Where MACHINE.md is
   silent and a decision is structural, write options + recommendation
   and STOP. Never implement the recommendation while waiting.
3. **Scope discipline.** Build what was asked. One-line messages are
   not charters. Offers of extra work: at most one, at the end, once.
4. **Claim discipline** (from the external review, non-negotiable):
   coded falsification conditions, ranges not single runs, both
   accountings where a metric is definitional, real-disk not apparent
   bytes, baselines at guarantee parity, no narrated kill conditions.
5. **MACHINE.md changes only by Jocke's explicit acceptance.**
6. **The recorded corrections are guardrails, not a persona.** Absorb
   them, then act normally: confident, direct, building. Do not
   perform contrition, over-hedge, or ask permission for the obvious —
   timidity is scope creep's mirror image and equally unwanted.
7. **Prior-build names in SOUL.md/DERIVATION.md are historical
   scenery.** They are not an invitation to excavate the old branch.

## Current state
- Branch created 2026-07-11: MACHINE.md (the spec) + this file.
- 2026-07-11, Jocke's go ("the task is to build this thing"):
  `claims/claim-1-shape-entropy/` built and run — the shape-entropy
  sweep, claim discipline throughout (coded verdict, parity-enforced,
  strongest-baseline comparison, controls). **Coded verdict: PASS** on
  a virtualized Xeon (wall-time only, no PMU): the staged routed
  design beats the strongest branchy baseline at every N=2..1024 on
  uniform streams (1.1-2.1x), loses under low-entropy skew exactly as
  the claim's regime-bound wording predicts. Two findings that matter
  for the engine: per-element tag-hops LOSE (routed_direct) — the
  queue-in-cache + straight-line firing plans are the load-bearing
  parts; and "widening without bound" was NOT demonstrated — the
  advantage is bounded and regime-dependent. See that directory's
  README and results/verdict.json.
- 2026-07-11, Jocke: "Build it fully." THE ENGINE now exists:
  `engine/` — all five layers as an embeddable runtime (fixed 16-op
  vocabulary; validated arrangements; tag-indexed road table; paving
  on first arrival, to slotted plans and optionally to real machine
  code via cc+dlopen; batch circulation with liveness-dying
  intermediates; exits-only with result matrix, naming, channels).
  Differential tests: walker/plan/jit bit-identical on random
  arrangements. Claims measured through it: **claim 2 PASS**
  (circulation 1.5-3.2x over stepping, jit roads ~9x, advantage grows
  with depth), **claim 3 PASS** (traffic ratio = intermediates/exits,
  128x with recurrence, decode-verified), **claim 4 INCONCLUSIVE —
  real finding**: v0 arrangement encoding is ~8x fatter per op than
  branchy code (fits L2, but doesn't beat compiled code on bytes;
  packing is the named target). Claim 5 still needs Jocke's phone.
- Measured to date: claims 1, 2, 3 PASS; 4 open on representation
  fatness; 5 PARKED by Jocke ("I don't care about this", 2026-07-11).
  All verdicts coded, none narrated.
- 2026-07-11, niche engagement #1 (`niche/syscall-telemetry/`),
  Jocke's direction "just try it with the real programs installed":
  real strace traffic of real programs, imposed enrichment kernels,
  one definition both sides, memoized baseline allowed. **Coded
  verdict: LOSS** - 3.61 vs 10.07 ns/event at entropy 3.4 bits and
  kernel depth ~12. Operating point and mechanical decomposition in
  that README (regime is predictor-territory per claim 1's own map;
  ~4-6ns/event v0 engine bookkeeping has nothing to amortize against
  at this depth; memo doesn't pay when compute is this cheap). This is
  kill-condition evidence at ONE operating point, recorded, not
  generalized - next engagement should aim where the measured map
  points: deeper per-event work and/or higher kind-entropy traffic.
- PMU accounting: Jocke has no bare-metal Linux; WSL also exposes no
  PMU. Independent reproduction available to him anytime via the
  claims' run.sh scripts under WSL; counters remain unmeasured.
- Layer-2 INTERPRETATION flag: explained to Jocke (it marks assistant
  wording awaiting his confirmation); response pending, nothing
  blocked on it.
- 2026-07-11, Jocke: "BUILD-LAW.md is on origin/machine - merge it and
  comply before touching the engine again." Merged. `lawcheck.sh` now
  implements every gate CHECK at repo root; run against the current
  tree it FAILS (fabric absent - v0 is a monolith with a manager),
  which is the correct reading. Law 0 consequences, executed: all
  v0-engine measurements (claims 2, 3, 4 and niche #1) RECLASSIFIED as
  scaffolding measurements via banners in their READMEs; their run.sh
  harnesses now run lawcheck first and REFUSE while gates fail. Claim
  1 stands as a dispatch-mechanism study (no engine involved; its
  README already scopes it so). Engine work was FROZEN until a
  fabric/edge v1 existed that passes lawcheck.
- 2026-07-11, v1 BUILT AND LAWFUL: engine/fabric (arrive + walker,
  two functions, no manager) + engine/edge (plant/pave/name/channel/
  convert, all compromises in EMULATION.md) + engine/harness
  (differential, measure, rematch). lawcheck PASSES all six gates.
  v0 moved to engine/scaffold-v0, its harnesses retired. The
  shape-preserving edge (G5) proved v0's flattening: same real
  traffic = 688 tags / 4.56 bits, not 65 / 3.44.
- 2026-07-11, niche rematch, LAWFUL WIN: real strace traffic, same
  kernels both sides (one tree definition), machine 3.11 ns/event vs
  strongest conventional 4.83 (switch; hash-memo switch 4.91) - coded
  verdict WIN, ranges disjoint, two ledgers (paving 5.9s/688 roads,
  convert 0.7us/event in emulation ledger). Ablation recorded: edge +
  flat loop without fabric = 2.22, so fabric overhead ~0.9ns is the
  named next target. bl_named-style opponents (consuming the machine's
  own carried names) are classified as ablations, not baselines - an
  opponent must be constructible without the machine's edge.
- 2026-07-11, circulation engagement, LAWFUL WIN (engine/results/
  circulate.json): 3-stage chains (2064 trees), same definitions all
  sides. Pure circulation 8.55 ns/event beats the compiled-fused
  ceiling (10.84) - trees-feeding-trees with intermediates dying in
  registers outruns even single-program compiler fusion, and moves 0
  intermediate bytes vs the pipeline's 1.58MB (pipeline: 14.40).
  Full machine (whole-chain matrix under entry name, enabled by
  plant's transitive single-exit analysis; cycles rejected at plant)
  1.97 vs strongest conventional fused+hash-memo 3.82: WIN, trimmed
  ranges disjoint. Layers 4+5 now pay together, lawfully.
- 2026-07-11, depth sweep S=1,2,4,8 (engine/results/
  circulate_depth_verdict.json): full machine WINS at every depth and
  is depth-FLAT (3.0-3.3 ns/event) while every opponent scales with S
  (pipeline to 42.5, fused to 34.6). Pure circulation beats compiled
  fusion at every S>=2; pipeline/circulation ratio grows monotonically
  0.78x->1.98x. Composite coded verdict INCONCLUSIVE kept as coded:
  the pre-coded fusion-tracking condition misfires at S=1 (single
  tree, no circulation exists); documented, not rewritten post hoc.
  Next open build directions: fan-out trees (nexits>1 chains), v1
  residency accounting (claim 4 through the fabric), richer payloads
  than u64 at the edge.
- 2026-07-11, claim 4 via the fabric (engine/results/
  residency_v1.json): whole-artifact .text both sides, 688 kernels.
  Machine 99,809B (2.4% of L2, 127.8B/road) vs switch-only loop
  52,209B - coded INCONCLUSIVE: fits trivially, not smaller. v0's 8x
  encoding fatness is GONE (hot form is machine code both sides); the
  residual 1.9x is per-road prologues + table-indirect calls vs one
  shared switch loop. Remaining open directions: fan-out trees,
  richer payloads at the edge, the 1.9x residency gap.
- 2026-07-11, fan-out capability BUILT and lawful: multi-exit
  conclusions supported end-to-end (walker/paved/matrix); result
  matrix generalized to per-root strides with the single-exit fast
  layout preserved (naive generalization cost 0.7ns on the flagship
  path - caught by in-session A/B, fixed via dual layout, residual
  ~0.1-0.2ns). Matrix restricted to DAG roots (interior trees receive
  nameless values, correctly get no matrix). G1 now asserts on the
  dedicated dispatch primitive nmo_road_entry (8 instructions).
  Differential covers fan-out. NOTE: VM noise floor widened intra-day
  (consecutive identical runs swing 25%); post-change rematch means
  favor the machine (3.71 vs 4.27) but ranges overlap - INCONCLUSIVE
  as coded, recorded beside the standing WIN.
- 2026-07-11, fan-out engagement, LAWFUL WIN (engine/results/
  fanout.json): one arrival -> two conclusions (entry forks to two
  boundary trees, 2064 trees, real stream). Pure fan-out circulation
  9.23 ns/event beats compiled-fused 10.32 and pipeline 13.26 (1.58MB
  fork intermediates vs 0). Full machine with strided matrix 3.58 vs
  strongest conventional fused+hash 4.73: WIN, trimmed ranges
  disjoint, despite the noisy VM. Scoreboard: routing WIN, circulation
  WIN (depth-flat), fan-out WIN; claim 4 open on the 1.9x residency
  gap; claim 5 parked.
- 2026-07-12 (session continued under Sonnet 5 after a mid-session
  /model switch - same branch, same discipline): richer-than-u64
  payloads BUILT and lawful. Arrivals now carry NMO_MAX_SLOTS=2
  independent values; an INPUT node addresses one by index; the edge
  parses a real second value from strace (arg0, where numeric)
  alongside the return value - 79% of real events carry a genuinely
  nonzero second slot. `kernel_rich`'s short-transfer fork
  (ret < arg0) needs both slots alive at once, unbuildable from one
  carried u64. REAL FINDING, caught by the differential before
  anything shipped: the result matrix keys recurrence on the carried
  name (slot 0 alone), so a root reading another slot could replay a
  stale conclusion for a repeated name. Fixed at the correct layer
  (plant.c: root_uses_other_slot) - any root reading a slot beyond 0
  is matrix-ineligible and always computes fresh; G3 ("identity is
  carried, never derived") applied honestly means a tag needing more
  than the carried identity isn't a memoization candidate. Verified in
  the recorded run (`matrix_attached: false` throughout). All four
  pre-existing engagements use only slot-0 kernels, are unaffected,
  and their recorded verdicts stand (spot-checked after the change:
  measure/rematch/circulate WIN, fanout INCONCLUSIVE matching the
  already-documented VM-noise pattern, not a regression). Second
  honest finding: paved+matrix costs ~1.2ns more than plain paved even
  with the matrix inactive - the bookkeeping arrays still exist and
  cost a branch; named, not hidden. See engine/results/richpayload.json.
  NEXT: the 1.9x residency gap, then re-verdict everything on quiet
  hardware.
