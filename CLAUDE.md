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
- No engine exists. Claims 2-4 unmeasured; claim 5 needs Jocke's
  phone. Next structural decisions (engine host form, first niche,
  claim order) are Jocke's; options written, awaiting his ruling.
