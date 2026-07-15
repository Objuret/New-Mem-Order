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
   script (`lawcheck.sh`, repo root), and Law 0 — no number is ever
   reported as the machine's while a gate fails.
5. `STATE.md` — the full operational record: architecture as built,
   every measured number with its verdict and operating point, the
   findings that cost something, open work in order, how to work here,
   the vocabulary, and the dated register of Jocke's rulings. It is
   subordinate to documents 1-4. Everything below is the compressed
   version of it.

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

The same quarantine now applies to `engine/scaffold-v0/` — the retired
first build of THIS branch. Its numbers are reclassified scaffolding
data (Law 0 banners mark them); its harnesses refuse to run. It exists
as the cautionary artifact BUILD-LAW was written from.

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
8. **Report style, per Jocke's explicit correction:** "Less essay,
   more improvement." Lead with verdict and numbers; decompose losses
   mechanically; never bury one; keep chat short (he reads from a
   phone) — depth goes in the repo. Baselines must be constructible
   without the machine's edge; the machine-minus-a-layer is an
   ablation and is labeled so.

## How to work here (the rest is STATE.md §8)
```
./lawcheck.sh        # FIRST. Engine work and numbers are forbidden
                     # while it fails (Law 0).
make -C engine test  # the differential: walker == paved, matrix
                     # on == off, order exact. Run after EVERY
                     # fabric/edge change - it has caught real
                     # corruption before it shipped.
./reproduce.sh       # the whole lawful suite, coded verdicts, ~15 min
```
Fabric changes additionally get an in-session A/B of the flagship
rematch (old vs new in one session — this VM's noise floor swings 25%
across sessions, so cross-session deltas are not evidence).

Needs Jocke, never unilateral: MACHINE.md changes; removing the
Layer-2 INTERPRETATION flag; structural decisions where the spec is
silent (options to OPTIONS.md, then STOP); touching either prior
build; reopening claim 5.

## Current state (2026-07-12 — full record and numbers in STATE.md §5-7)
- **The machine exists and is lawful**: `engine/fabric` (arrive +
  walker + dispatch primitive, nothing else) + `engine/edge` (every
  compromise, registered in EMULATION.md) + `engine/harness`. All six
  gates PASS. Arrivals carry 2 value slots; trees fan out; chains
  circulate road-to-road; cyclic wiring is rejected at plant, so every
  firing provably terminates; the result matrix replays whole-chain,
  multi-exit conclusions by carried name, and refuses roots whose
  conclusions the carried identity doesn't cover.
- **Scoreboard, all coded, all on real traffic** (strace of this box's
  real programs; 98,733 events, 688 shape tags, 4.56 bits):
  routing **WIN** (3.11 vs 4.83 ns/event), circulation **WIN** (1.97 vs
  3.82; pure circulation 8.55 beats even compiled fusion 10.84;
  depth-FLAT 3.0-3.3 at S=1..8 while opponents scale to 42.5), fan-out
  **WIN** (3.58 vs 4.73), all trimmed-range disjoint; residency
  **INCONCLUSIVE** (99.2B/road, 1.9% of L2, but 1.54x the branchy
  bytes); claim 1 **PASS** (its own apparatus); claim 5 **PARKED** by
  Jocke. One honest v0 LOSS stands reclassified as scaffolding data.
- **Verify anything** with `./reproduce.sh` (its own verification run
  re-verdicted rematch/circulate/fanout as WINs fresh).
- **Open, in order** (STATE.md §7): quiet-hardware re-verdict (one
  command, needs a machine); Layer-2 ratification (one line, needs
  Jocke); niche engagement #2 aimed at deeper/higher-entropy real
  traffic; multi-value interior handoffs (structural — options first);
  the 1.54x residency residual; vocabulary-pressure watch (THE
  standing kill threat).
