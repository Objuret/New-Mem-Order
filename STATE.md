# STATE — the full operational record of THE MACHINE (branch: machine)

This is the state document: everything a fresh agent needs to continue
the work without the conversation that produced it. It is subordinate
to the founding documents — where anything here disagrees with
SOUL.md, DERIVATION.md, or MACHINE.md, they win, in that order — and
BUILD-LAW.md binds every line of engine work regardless of anything
written here. CLAUDE.md is the short orientation; this is the deep
record it points into.

Last full update: 2026-07-12. Every number in this file comes from a
recorded run in the repo (`engine/results/`, `claims/*/results/`,
`niche/*/results/`); none is narrated from memory. If a number here
ever disagrees with a results file, the results file wins.

---

## 1. What this project is

One premise (Jocke, 2026-07-11): *"What the fuck is data if not
code?"* There is no physical code/data distinction — one memory, one
kind of byte. Hardware treats bytes reached as code royally because
they arrive with promises (immutable, stable identity, visible
recurrence, vetted). THE MACHINE makes ordinary data give the same
promises, so it qualifies for the same machinery — and for machinery
the hardware doesn't have yet.

Five layers (MACHINE.md is the spec; read it, then DERIVATION.md to be
able to RE-derive it — an agent that can't re-derive it will
reinterpret it into whatever it already knows):

1. **Roads** — a program's finite path network held resident, each
   road a pre-staged straight-line firing plan. Novel shapes take the
   single slow walker once; arrival = paving.
2. **Tags** — data announces its road; routing is an indexed hop,
   never payload inspection. Value-forks stay honest computation.
   (Formalization still flagged INTERPRETATION — awaiting Jocke.)
3. **Residency & arrangement** — the vocabulary is installed once,
   permanently; a tree adds only which-parts-connected-how.
   Arrangement is information-theoretically tiny.
4. **Circulation** — the program plants once and leaves the loop; data
   circulates through resident trees, intermediates dying in
   registers, tree topology IS control flow.
5. **Exits** — only conclusions cross any boundary, as names when the
   far side holds the value; the result matrix is grown by occurrence,
   never prophecy.

Safety condition: data can only ARRANGE a fixed, vetted vocabulary —
it can never mean "execute arbitrary bytes." This is what makes
dissolving the code/data boundary survivable, and (as built) acyclic
wiring over that vocabulary also makes every firing provably
terminate.

Kill conditions (MACHINE.md, verbatim intent): unbounded per-element
verbs; real-world recurrence/shape-entropy too low to pay; claim 1
failing its sweep; failing to win one niche on measured advantage.

## 2. Repository map

```
MACHINE.md        the spec - changes ONLY by Jocke's explicit acceptance
DERIVATION.md     the reasoning chain + the five corrections (read to re-derive)
SOUL.md           the founding conversation, both voices (primary source)
BUILD-LAW.md      BINDING: six mechanical gates + Law 0 (see §3)
CLAUDE.md         orientation for a fresh session (short; points here)
STATE.md          this file
README.md         two-paragraph human landing page
lawcheck.sh       mechanical enforcement of BUILD-LAW; harnesses run it
                  first and refuse on failure
reproduce.sh      one command: gates -> differential -> all engagements
                  -> residency, printing every coded verdict (works on
                  any Linux with gcc+python3, e.g. Jocke's WSL)

engine/
  fabric/         THE MACHINE PROPER. fabric.h (types, vocabulary,
                  arrive path) + fabric.c (arrive, the dispatch
                  primitive, the walker). Two functions on purpose:
                  nothing for administration to live in. Gate-linted.
  edge/           every silicon compromise, registered in EMULATION.md:
                  plant.c (validation, allocation, matrix layout,
                  cycle rejection), pave.c (cc+dlopen paving), name.c
                  (interning - the only place identity is computed),
                  channel.c (boundary wire: value once, name after),
                  convert.c (strace text -> arrivals, shape-preserving)
  harness/        measurement. differential.c (correctness), measure.c
                  (two ledgers + gate asserts), rematch.c / circulate.c
                  / fanout.c / richpayload.c (engagements),
                  residency.sh (claim 4), depth_verdict.py, kernels.h
                  (one kernel definition shared by machine and
                  baselines - parity by construction)
  results/        recorded runs: rematch.json, circulate.json,
                  circulate_depth_verdict.json, fanout.json,
                  richpayload.json, residency_v1.json, measure.json,
                  rematch_fanout_fabric.json, environment.txt
  scaffold-v0/    the RETIRED first build (see §5.1). Historical data
                  only; its harnesses refuse unconditionally.
  EMULATION.md    the register of compromises (G6 requires it)

claims/
  claim-1-shape-entropy/   the dispatch-mechanism study (no engine
                           involved; lawful as scoped). PASS, recorded.
  claim-{2,3,4}-*/         v0-era harnesses, RETIRED under Law 0;
                           recorded results reclassified as scaffolding
                           data (banners in each README)

niche/syscall-telemetry/   niche engagement #1 (v0-era LOSS, Law 0
                           banner; the real-traffic capture lives here:
                           capture.sh, edge.py, records.bin(.gz))
OPTIONS.md                 decision register (options-first rule);
                           historical rulings recorded inline
```

## 3. The law (BUILD-LAW.md) and how it is enforced

Twenty builds by two agents proved the founding docs produce correct
confessions, not correct builds: under pressure, the builder's
scaffolding (managers, queues, batching, computed identity, flattened
edges) silently replaces the machine and its losses get reported as
the machine's. BUILD-LAW removes builder judgment: mechanical gates,
checked by script.

**Law 0:** no measurement may be reported, recorded, or summarized as
a result "of the machine" while any gate fails. A number produced
under a failing gate is a measurement of scaffolding. If a gate can't
pass on this silicon, the honest output is "unmeasurable here, because
<gate>" — never a number.

The six gates and their mechanical checks (`lawcheck.sh`, repo root —
run it before ANY engine work; every measurement harness runs it first
and refuses on failure):

| gate | property | mechanical check |
|---|---|---|
| G1 | no manager: arrival -> road entry is one indirect dispatch | banned-token lint on `engine/fabric/*` (queue/buffer/callback/sink/sched/drain/batch/...); instruction budget asserted on the dedicated dispatch primitive `nmo_road_entry` (whole symbol, counted by objdump at build: currently **8 instructions**, budget 40, marker `LAW_G1_DISPATCH_BUDGET` in measure.c) |
| G2 | per-arrival, order untouched; exits carry name+value and nothing else | order/provenance token lint on fabric; wire-byte assert (`LAW_G2_EXIT_BYTES`): ≤12B per exit on the channel |
| G3 | identity carried, never computed | hash/compare token lint on fabric (hashing lives only in edge/name.c) |
| G4 | circulation real: no allocation/serialization between stages | malloc/serialize lint on fabric; runtime heap assert across the arrive loop (`LAW_G4_NOALLOC`, mallinfo2) |
| G5 | the edge preserves shape | edge must compute and emit `entropy_before` and `entropy_after` side by side, always |
| G6 | two ledgers, structurally separated | engine sources only under fabric/+edge/; fabric may not include edge; every edge module named in EMULATION.md; harness output has `machine_account` and `emulation_account` |

Practical notes a fresh agent WILL hit:
- The lint greps hit comments and identifiers alike. Fabric code
  (including comments) must avoid the banned words. Lists are
  append-only by policy — grow them when a new scaffolding species
  appears; never trim.
- The G1 counter measures `nmo_road_entry` as its own symbol because
  the earlier count-to-first-call proxy conflated layer-5 matrix
  replay (conclusions that never reach a road) with dispatch.
- v0's numbers were retroactively reclassified under Law 0 (banners in
  their READMEs); their harnesses refuse unconditionally so a
  gate-passing tree can't accidentally mint fresh v0 numbers.

## 4. Architecture as built (v1, lawful)

### 4.1 Fabric (`engine/fabric/`)

Types (fabric.h): `nmo_node` {op, slot, a, b, c, imm}; `nmo_tree`
{tag, nodes[≤256] in topological order (operands always earlier),
exits[≤8] with per-exit `exit_to` = NMO_EXIT_BOUNDARY or another tag};
`nmo_road` {fn, tree}; `nmo_fabric` {road table, exit cursor, result
matrix (two layouts), name_span}.

Vocabulary: 16 fixed ops — INPUT (reads arrival slot `nd->slot`),
CONST, SELECT (the honest value-fork: a ? b : c), and 13 binops
(ADD SUB MUL AND OR XOR SHL SHR ROTL EQ LT MIN MAX) defined ONCE in
the `NMO_BINOPS` X-macro. The walker, the paver's codegen, and every
baseline emitter stringize the same expressions — parity by
construction, verified at runtime anyway.

Arrivals carry `NMO_MAX_SLOTS = 2` independent u64 values plus a
carried name (dense id assigned at the edge from slot 0). The arrive
path (`nmo_arrive_at`, inline; cursor travels by value so concluded
arrivals never touch fabric state):

1. No matrix, or name out of span → one indirect dispatch into the
   road. That's the whole path (G1).
2. Single-exit layout (`matrix_meta == NULL`, every root concludes
   once): known(tag,name) → replay one value from `matrix[tag*span+
   name]`; else fire, then insert if `matrix_ok[tag]`.
3. Strided layout (some root's chain concludes >1 exits):
   `matrix_meta[tag] = (offset<<4)|stride`; known → replay `stride`
   values; else fire and insert the last `stride` exits.

The dual layout exists because the naive generalization cost 0.7ns on
the flagship single-exit path (caught by an in-session A/B; the dual
layout restored it to ~0.1-0.2ns).

Roads fire whole trees; an exit either writes one bare value to the
exit region **in arrival order** (G2) or feeds another road directly —
value passed in registers, landing in slot 0 of the fed tree, other
slots zero (an interior tree only ever receives the one value its
feeder concluded). Interior values are nameless and unaddressable by
construction.

The walker (`nmo_walk_road`) is the single slow road: one op at a
time over the tree form. It serves any unpaved road forever,
correctly; the differential proves it bit-identical to paved code.

Termination: plant rejects cyclic exit_to wiring, so acyclic
arrangements over a fixed total vocabulary = every firing provably
terminates. The safety condition with teeth.

### 4.2 Edge (`engine/edge/`, all compromises in EMULATION.md)

- **plant.c** — validation at the door (vocabulary membership, arity,
  backward-only refs, slot bounds, exit targets, size caps), cycle and
  dangling-target rejection, transitive chain-exit counting (how many
  boundary exits one arrival at tag T ultimately produces), matrix
  allocation and eligibility. Matrix eligibility rules, all enforced
  here: only DAG roots (untargeted tags — interior trees receive
  nameless values); only chains concluding in 1..8 boundary exits; and
  **only roots whose own tree reads no slot beyond 0**
  (`root_uses_other_slot`) — because identity is carried from slot 0
  alone, a root depending on slot 1 would replay stale conclusions for
  a repeated name. That last rule exists because the differential
  caught exactly that corruption before it shipped (§6.7).
- **pave.c** — trees become straight-line machine code via cc + dlopen,
  one .so per fabric (`nmo_paved_<tag>` per road). Paving flags default
  to size-honest `-Os -falign-functions=1 -fcf-protection=none`
  (`NMO_PAVE_FLAGS` overrides): straight-line single-block roads gain
  nothing from -O2 or 16B alignment, and the padding/CFI pads were
  pure resident fat (measured: 127.8 → 99.2 B/road with rematch speed
  unchanged). Paving failure leaves the walker serving — correct, slow.
- **name.c** — interning. The ONLY place identity is computed; past it
  everything is a dense u32 name.
- **channel.c** — the boundary wire: novel value = name+value (12B),
  recurrence = name (4B); decode side reconstructs exactly (tested).
- **convert.c** — strace text → arrivals. The tag is the structural
  signature (syscall + argument classes), NOT just the syscall — G5's
  shape preservation; entropy before/after printed side by side.
  Slot 0 = return value (also the carried identity), slot 1 = first
  argument where it parses as a whole integer (79% of real events
  carry a nonzero slot 1; resumed lines and non-numeric args leave it
  0 — stated, not guessed).

### 4.3 Harnesses (`engine/harness/`) and measurement discipline

- **differential.c** — the correctness backstop. Random trees
  (including fan-out, road-feeding, SELECT, both slots), recurrence-
  heavy stream: walker vs paved, matrix on vs off, must be
  bit-identical with exact exit order; safety rejections; channel
  round-trip. RUN THIS AFTER EVERY FABRIC/EDGE CHANGE. It has caught
  one shipped-would-have-been-corruption (§6.7) and one crash.
- **measure.c** — two ledgers + the gate asserts (G1/G2/G4 markers).
- **Engagements** — rematch (flat routing), circulate (S-stage chains,
  depth-parameterized), fanout (one arrival → two conclusions),
  richpayload (two-slot kernels). Common protocol, learned the hard
  way and not optional:
  - Same tree definitions on all sides (kernels.h), baselines emitted
    from the same node lists and compiled -O2 into a .so; parity
    checked at runtime, abort on mismatch.
  - Opponent set: **a baseline must be constructible without the
    machine's edge.** The switch and the hash-memoized switch qualify
    (hashing is the honest conventional price of identity). A
    name-indexed cache consuming the edge's carried names does NOT —
    it is an ablation of the machine (edge + flat loop, no fabric)
    and is reported as such, never as the opponent.
  - Pipeline / fused / fused+hash-memo for multi-stage engagements:
    pipeline = the fragmented-system architecture (materialized
    intermediate arrays, bytes counted code-side); fused = the
    compiled ceiling (possible only when all stages are one program);
    fused+hashed = strongest conventional.
  - Timing: pin to CPU 0; self-warm each variant before its timed
    block (eviction by the previous variant is not this variant's
    cost); symmetric 1-rep trim (drop best and worst of every variant,
    declared pre-verdict, both sides); report mean/min/max.
  - Verdicts CODED, three-valued: WIN = machine max < opponent min
    (trimmed ranges disjoint); LOSS = reverse; else INCONCLUSIVE.
    Never rewritten after seeing data — a mis-specified condition is
    documented beside its result (see the S=1 misfire, §5.3).
- **residency.sh** — claim 4 through the fabric: whole-artifact .text
  both sides (symbol-level accounting lies — the inliner once made
  the baseline look like 65 bytes).
- **reproduce.sh** (repo root) — everything above, one command.

## 5. The measurement record

Environment for every number below: virtualized 4-vCPU Intel Xeon
@2.8GHz (cloud), 4MB L2 / 33MB L3, **no PMU exposed** (wall-time
accounting only; the harnesses read counters automatically where a PMU
exists), gcc 13.3, Ubuntu 24.04. The VM's noise floor swings up to
~25% intra-day; the trim/self-warm/ranges discipline exists because of
it, and verdicts are tied to their recorded runs. All engagements use
the same real traffic: strace of real programs on this box (gcc,
python, git, make, tar, find, grep, sha256/gzip) — 98,733 events, 688
structural-signature tags, entropy 4.56 of 6.02 possible bits, value
recurrence 94.5%, name span 4,566. The exact stream of record is
committed (`niche/syscall-telemetry/records.bin.gz` for the v0 run;
v1 runs re-convert from `traces/`, re-capturable via capture.sh).

### 5.1 The v0 story (scaffolding — reclassified, kept as history)

v0 (`engine/scaffold-v0/`) was all five layers as an embeddable
runtime with a manager, staging queues, batching with provenance
metadata, and computed identity. Its record: claims 2 and 3 "PASS,"
claim 4 INCONCLUSIVE (arrangement encoding ~8x fatter per op than
branchy code), and niche #1 on real traffic a **LOSS 3.61 vs 10.07
ns/event**. Under BUILD-LAW (merged after those runs) every v0 number
is a measurement of scaffolding composed with the machine's
mechanisms; banners mark each README and the harnesses refuse. The
diagnosis that led to the gates: the builder's compensations — not
the machine's layers — were what the losing measurements measured.
Keep v0 only as the cautionary artifact it is.

### 5.2 Claim 1 — routing vs prediction (dispatch study; no engine)

**PASS** (claims/claim-1-shape-entropy/, coded verdict). Staged
routing (queue-in-cache + straight-line plans) beats the strongest
branchy baseline at every N=2..1024 on uniform streams (1.09x at N=2,
peak 2.02x at N=8, 1.40x at N=1024); loses 1.73x under 99%-skew
exactly as the regime-bound claim predicts (predictor recovery
confirms mechanism attribution); win survives -fno-tree-vectorize;
per-element indirect hops (`routed_direct`) LOSE everywhere — staging
is load-bearing, not tag-lookup alone. "Widening without bound" was
NOT demonstrated: the advantage is bounded and regime-dependent.
Note: v1 later proved per-arrival dispatch CAN win when the manager
is removed — claim 1's "staging is load-bearing" holds within its
apparatus (bare loops, no fabric); the two results are about
different mechanisms and do not contradict.

### 5.3 The lawful v1 scoreboard (all under passing gates)

| engagement | machine | strongest conventional | verdict |
|---|---|---|---|
| **rematch** (flat routing, 688 kernels) | 3.11 (2.82–3.81) | switch 4.83 / hash-memo 4.91 | **WIN**, disjoint |
| **circulate** (3-stage chains, 2064 trees) | full 1.97; pure circulation 8.55 | fused+hash 3.82; fused 10.84; pipeline 14.40 + 1.58MB intermediates (machine: 0) | **WIN**, disjoint |
| **depth sweep** S=1/2/4/8 | 3.04 / 3.12 / 3.31 / 3.31 (depth-FLAT) | pipeline 4.5→42.5, fused 4.7→34.6, fused+hash 4.6→5.9 | WIN at every S; composite INCONCLUSIVE — pre-coded fusion-tracking condition misfires at S=1 (single tree, no circulation exists); kept as coded, documented |
| **fanout** (1 arrival → 2 conclusions) | full 3.58; pure 9.23 | fused+hash 4.73; fused 10.32; pipeline 13.26 + 1.58MB | **WIN**, disjoint |
| **richpayload** (two-slot kernels) | paved 5.07 (walker 30.79) | two-arg switch 4.47 | capability engagement, no speed verdict claimed; correctness + gates; matrix correctly ineligible (see §6.7) |
| **residency** (claim 4 via fabric) | 80,485B total, 99.2B/road, 1.9% of L2 | switch-only loop 52,209B | **INCONCLUSIVE**: fits trivially, not smaller (1.54x); predictor-state half unmeasurable, recorded as unmeasured |

Key structural readings, each from a recorded run:
- **Pure circulation beats compiled fusion at every S ≥ 2** — trees
  feeding trees in registers outruns single-program compiler fusion,
  at 0 intermediate boundary bytes.
- **The full machine is depth-flat** (~3.3ns at 8 stages) while every
  opponent scales with depth; pipeline/circulation ratio grows
  monotonically 0.78x → 1.98x.
- **Ablation** (edge + flat named loop, no fabric): 2.22 ns — the
  fabric's arrive overhead is ~0.9ns on the flat engagement; a named
  target, not hidden.
- The reproduce.sh verification run (2026-07-12) re-verdicted fresh on
  this VM: rematch WIN 2.72 vs 4.62, circulate WIN 2.79 vs 5.59,
  fanout WIN 5.21 vs 7.06 (disjoint — the one earlier fanout
  INCONCLUSIVE, recorded in rematch_fanout_fabric.json, was VM noise
  as documented).
- Emulation ledger, never blended into the machine's: paving ~6s per
  688 roads (~14s for 2064; scales with cc invocation), convert
  ~0.7µs/event (strace TEXT parsing — real deployments feed binary),
  boundary wire 4.55 B/exit on this recurrence.

### 5.4 Claim-by-claim status

1. Routing beats prediction at high shape-entropy: **PASS** (5.2).
2. Circulation beats program-mediated stepping: v0 "PASS" reclassified;
   superseded by the LAWFUL circulate/depth WINs (5.3), which are
   stronger (beat fusion, not just stepping). Wall-time only —
   instructions/energy named by the claim remain unmeasured here.
3. Exits-only collapses traffic: v0 "PASS" reclassified; the lawful
   record shows 0 intermediate boundary bytes vs 1.58MB per pipeline
   engagement, and the channel's 4.55 B/exit. A dedicated lawful
   claim-3 sweep (ratio vs depth) has not been re-run; low priority
   since the mechanism is embedded in every engagement's accounting.
4. Arrangement-residency fits: **INCONCLUSIVE** and open — fits L2 at
   1.9%, but 1.54x the branchy artifact's bytes. Residual ~47B/road is
   the structural price of independently callable roads (ret +
   exit-write + symbol). The claim's "plus predictor state cannot"
   clause is unmeasurable from software; a PMU host could argue it
   with misprediction data instead of bytes.
5. Movement is energy: **PARKED by Jocke** ("I don't care about this,"
   2026-07-11; later: interesting "only if no other metric exists").

## 6. Findings that must shape future work (each cost something)

1. **The manager was the loss.** v0's 10.07 vs 3.61 defeat decomposed
   into ~4-6ns/event of engine bookkeeping. Removing the manager (v1
   fabric: one arrive path, no queues, no callbacks) turned the same
   fight into a WIN. Any convenience layer that touches the per-event
   path will eat the machine's entire margin.
2. **The edge can destroy the regime.** v0's edge flattened real
   traffic to 65 tags / 3.44 bits and we measured "reality has no
   entropy." The shape-preserving edge found 688 tags / 4.56 bits in
   the SAME bytes. Conclusions about the world are conclusions about
   your conversion until proven otherwise (G5 exists for this).
3. **Baseline classification is load-bearing.** A "baseline" consuming
   the machine's own carried names is an ablation, not an opponent.
   The honest conventional memoizer pays hashing. Getting this wrong
   flips verdicts in either direction.
4. **The compiler will lie to your accounting.** Symbol-size
   measurements made the branchy baseline look like 65 bytes (outlined
   dispatcher). Whole-artifact .text on both sides, always.
5. **Generalizations tax the hot path silently.** The strided matrix
   cost 0.7ns on the single-exit path until the A/B caught it; the
   inactive matrix still costs ~1.2ns of bookkeeping on rich-payload
   fabrics. Every fabric change gets an in-session A/B against the
   flagship engagement (same session — the VM drifts across sessions).
6. **This VM's noise is real**: identical runs swing up to 25%
   intra-day. Trimmed ranges, self-warm, in-session A/Bs, and
   verdicts-tied-to-runs are the countermeasures. Cross-run deltas
   without an in-session control are not evidence.
7. **Identity must cover the conclusion** (the multi-slot lesson). The
   matrix keys on the carried name = slot 0's identity. A root whose
   tree reads slot 1 can conclude differently for a repeated name —
   the matrix would replay stale results. plant.c excludes such roots
   from memoization (root_uses_other_slot). The differential caught
   this before it shipped; the general rule: any extension that adds
   information to an arrival must either extend carried identity to
   cover it or exclude the affected roots from the matrix.
8. **Verdict conditions are code, written before data.** When one
   misfires (the S=1 fusion-tracking clause), the INCONCLUSIVE stands
   and the misfire is documented next to it. Rewriting conditions
   after seeing results is the exact failure the external review
   punished.
9. **Interior handoffs are single-valued** (as built): road-to-road
   passes one conclusion into slot 0, other slots zero. A fed tree
   needing more than one value from upstream is currently
   inexpressible — a known, stated limit (see §7 open work), not an
   accident.

## 7. Open work, in order of value

1. **Quiet-hardware re-verdict.** Everything is one command:
   `./reproduce.sh` on any Linux with gcc+python3. A PMU-bearing host
   additionally unlocks branch-miss/instruction accounting (harnesses
   auto-read) and the only honest attack on claim 4's predictor-state
   clause. Blocked on hardware access, not on code.
2. **Layer-2 ratification** — the INTERPRETATION flag in MACHINE.md is
   assistant wording awaiting Jocke's yes/correction. One line from
   him closes it (or triggers a routing-surface rebuild to his
   correction). Only he can do this; do not remove the flag yourself.
3. **Niche engagement #2** — the kill-list still wants a win outside
   our own harness definitions. The measured map says aim at deeper
   per-event work and/or higher kind-entropy traffic than syscall
   telemetry (real message buses, parsers, enrichment pipelines with
   lookups). The edge pattern (convert once, entropy before/after) and
   the opponent rules (§4.3) are the template. Real traffic only —
   synthetic streams can flatter forever.
4. **Multi-value interior handoffs** — trees that feed a downstream
   tree more than one value (fan-in / joins). Structural: MACHINE.md
   is silent on whether an interior tree may receive from multiple
   feeders (that's a dataflow join with ordering semantics). Per
   working rule 2: write options + recommendation, STOP for Jocke.
5. **Residency residual** (claim 4): ~47B/road structural overhead vs
   the shared-loop artifact. Next honest attack is shared epilogues /
   section merging at pave time — diminishing returns; the PMU
   argument (point 1) is more likely to settle the claim as stated.
6. **Vocabulary pressure** — THE standing threat (per-element-verb
   linearity). Every niche engagement should record whether its
   kernels fit the 16-op vocabulary comfortably or strained it. The
   day a real niche needs vocabulary growth per workload, the kill
   condition is live and must be reported as such.
7. **Claim 5** — parked; revisit only if Jocke reopens or all other
   metrics are exhausted.

## 8. How to work here (operational)

Build & verify (do this before believing anything):
```
./lawcheck.sh                 # must PASS before engine work or numbers
make -C engine                # builds fabric, edge, all harnesses
make -C engine test           # differential (correctness backstop)
./reproduce.sh                # full lawful suite, ~10-20 min
```

After ANY fabric/edge change, in this order: lawcheck → differential →
in-session A/B of the flagship rematch (old vs new, same session) →
engagements you touched → commit with the numbers in the message.

Adding an engagement (the checklist every existing one follows):
one kernel definition in kernels.h used by BOTH sides; baselines
emitted from the same node lists, compiled -O2; opponents
constructible without the edge (ablations labeled as ablations);
parity at runtime with abort; pinned CPU, self-warm, trimmed ranges;
coded three-valued verdict written BEFORE running; two ledgers in the
output; results JSON committed under engine/results/; README + this
file updated; harness refuses under failing gates.

What needs Jocke and must NOT be done unilaterally: any change to
MACHINE.md; removing the Layer-2 INTERPRETATION flag; structural
decisions where the spec is silent (write options + recommendation to
OPTIONS.md and STOP); touching the prior-art branch
(claude/build-it-r1yzg9); reopening claim 5.

Git: work on the designated session branch; commit messages carry the
numbers and the honest caveats (they are part of the record); push
after every landed unit. The stop-hook nags about uncommitted files —
that is correct behavior here, not noise.

Report style Jocke expects (he said it): "Less essay, more
improvement. The target is the concept." Lead with the verdict and
the numbers; decompose losses mechanically; never bury a loss; one
offer of extra work at most, at the end. He reads from a phone — keep
chat output short; put depth in the repo, not the reply.

## 9. Vocabulary (the words mean these things here, nothing else)

- **road** — one tree's executable form; **road table** — tag-indexed
  array of {fn, tree}; **paving** — compiling a tree to straight-line
  machine code (cc+dlopen at the edge); **walker** — the single
  generic interpreter, the slow road that always works.
- **arrival** — (tag, name, slots[2]) entering the fabric; **tag** —
  dense index naming the shape/road; **name** — dense identity
  assigned at the edge from slot 0; carried, never computed inland.
- **circulation** — a value moving road-to-road inside the fabric,
  in registers, nameless; **exit** — a value crossing the fabric
  boundary, bare, in arrival order; **channel** — the wire encoding
  (value once, name after); **boundary** — anywhere bytes leave.
- **result matrix** — per-root name-indexed conclusion replay, grown
  by occurrence; **stride** — exits per firing of a root's chain.
- **fabric / edge** — the machine proper / the registered compromises;
  **two ledgers** — machine_account vs emulation_account, never mixed.
- **engagement** — a measured fight against conventional opponents on
  real traffic with a coded verdict; **ablation** — the machine minus
  a layer, measured for attribution, never presented as an opponent.
- **scaffolding** — builder convenience that displaces the machine;
  the thing BUILD-LAW exists to make unexpressible.

## 10. Rulings register (Jocke's words are the axioms; dated)

| date | ruling (near-verbatim) | effect |
|---|---|---|
| 2026-07-11 | "The task is to build this thing. We will usher in a new paradigm of how computing is made." | the standing build charter |
| 2026-07-11 | "Build it fully." | full engine authorized; OPTIONS.md recommendations 1 and 2a taken as ratified |
| 2026-07-11 | "I don't care about this." (claim 5 / phone) | claim 5 parked |
| 2026-07-11 | "Just try it with the real programs installed then." | real-traffic niche protocol: strace of this box's real programs |
| 2026-07-11 | "I don't even understand your fucking issue here." (Layer-2 flag) | flag explained, stands until his explicit yes/correction — his statement is NOT ratification |
| 2026-07-11 | "BUILD-LAW.md is on origin/machine — merge it and comply before touching the engine again." | the law merged; lawcheck built; v0 reclassified; v1 rebuilt under gates |
| 2026-07-11 | "Build, improve, build, improve. Less essay, more improvement. The target is the concept." | the working cadence and report style |
| 2026-07-11 | "You report everything so fucking messy." | keep chat output short and plain; depth goes in the repo |
| 2026-07-12 | "create the full documentation ... also full /state doc, not just a light handoff" | this file and the CLAUDE.md rewrite |

Anything not in this table or the founding documents is assistant
judgment — treat it as testimony to re-derive, not doctrine.
