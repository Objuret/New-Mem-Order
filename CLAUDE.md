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
