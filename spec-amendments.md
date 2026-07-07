# Proposed Spec Amendments — from Run 2

`activation-model.md` is locked and has NOT been edited. These are proposed
lines arising from the run-1 review and run-2 rebuild, for Jocke to accept,
reword, or reject. The prototype currently implements all three, so
rejecting one means changing code, not just text.

## 1. Demand-by-reference is core machinery, not a structure

*Proposed addition to §2, under "Instruction" or "Reference":*

> Demanding by reference is part of the instruction form itself, not a
> member of the structure set. A demand names an unsent instruction; firing
> the demand reads it and fires it — demanding = reading = firing. The
> reference is a held name, never a computed one (A4).

Why: the review showed that a library-level `eval` (fire arbitrary
in-flight bytes) is a universal interpreter that freezes the §6 count
forever. But *demand* — fire the stored instruction a reference names — is
already mandated by §3 step 1 and A4. Placing it in the instruction grammar
keeps the §6 measurement meaningful: the structure set contains only
workload verbs, and nothing in it can fire values. Universality survives
only as "save an instruction, demand it," which is the model's own story
for what a program is.

## 2. Errors have a reserved form

*Proposed addition to §2 or §7:*

> A firing returns a value or an error, distinguishable by construction.
> The error form is reserved core machinery, like demand: a terminal whose
> world refuses (missing reference, refused write) yields an error, the
> whole indivisible firing aborts with it, and it propagates to the
> demander. Errors cannot be forged by content and cannot be confused with
> it.

Why: §4's "malformed is unexpressible" fully covers bad *bytes*, but a
well-formed firing can reach a world that says no, and the model previously
had no answer for what returns then (friction log #1). Convention-based
errors (an "ERR:" prefix) collide with content; this closes that hole with
one reserved node tag.

## 3. Topology qualifier for terminals

*Proposed amendment to §2 "Router" ("any topology works"):*

> Router count and placement are pure engineering **for pure firings**.
> Terminals that touch shared world-state (the same disk root, the same
> device) bind to one router: a firing is whole and indivisible, and one
> router serializing its terminals is what makes that hold at the edge
> where A2 stops.

Why: friction log #3. Two routers over one disk root would race their
write terminals — races reappeared exactly where writes reappeared. Inside
the model the no-coordination argument is airtight; this sentence keeps
the spec from claiming it past the edge.
