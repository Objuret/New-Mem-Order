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

## Current state
- Branch created 2026-07-11: MACHINE.md (the spec) + this file. No
  engine, no experiments, nothing else exists here yet.
- Next open item, awaiting Jocke's go and his priority order: the
  falsifiable claims in MACHINE.md (claim 1, the shape-entropy sweep,
  is the sharpest and cheapest; claim 5, energy, needs his phone).
