# THE MACHINE

Specification derived from Jocke's statements, conversation of
2026-07-11. His words are the source; each layer quotes them first and
formalizes second. Where the formalization goes beyond the quote, it is
marked INTERPRETATION and is provisional until Jocke confirms it.

This document is NOT continuous with the prior prototype (branch
`claude/build-it-r1yzg9`). That build is prior art: a storage-flavored
reading of the original concept documents, with a real measurement
record and a hostile external review. It is cited here only where a
measurement genuinely bears, and its vocabulary, code, and design
choices carry NO authority over this document.

---

## The premise

> "What the fuck is data if not code?"

There is no physical distinction between data and code — one memory,
one kind of byte. The machine treats them differently only because
bytes reached as code arrive with promises (immutable, stable identity,
visible recurrence, vetted) and bytes reached as data arrive with none.
Every layer below exists to let ordinary data make code's promises, so
it qualifies for the machinery the hardware reserves for code — and for
machinery the hardware doesn't have yet.

## Layer 1 — Roads

> "Couldn't a program emit or be interpreted to give a matrix of only
> its own possible combinations?" — "the SHAPES, not every single
> output, but the roads."

A program's road network — the finite set of paths/shapes it can
execute — is enumerable ahead of time, separate from the unbounded
values that flow through it. The machine holds the road network as an
explicit, resident artifact: every road pre-staged as a straight-line
firing plan with value slots. Novel shapes take the single slow road
(one generic walker) exactly once, which both answers them and PAVES
them — emits their compiled plan into the road table. Arrival = paving,
then forever after, routing.

## Layer 2 — Tags: data announces its road

INTERPRETATION (accepted in conversation): routing collapses to a
pointer hop only when the road choice does not require inspecting the
payload — the datum carries its shape tag on the surface. Two kinds of
forks are distinguished honestly: tag-forks (which kind of thing is
this?) cost one indexed lookup; value-forks (is it > 5000?) are real
computation, small, and never eliminable. The entire branch-prediction
problem class is deleted for routed traffic — not statistically,
structurally: the stream tells the machine where it is going.

## Layer 3 — Residency and arrangement

> "Cache is kinda meaningless, but can be used to store the queue
> instead, so the actual firing of the operations to the cpu can go
> faster." — "What if it's only made of structures of instructions...
> I was trying to convey concepts, not a specific thing."

The SRAM near the core stops being a passive mirror that guesses at
reuse and becomes deliberate residence: the structure vocabulary
(installed once, permanently) and the road network (trees over that
vocabulary). The load-bearing concept: **a tree is made of arrangement,
not material.** The parts are already resident; the only new
information a tree carries is which parts, connected how — and
arrangement is information-theoretically tiny. Consequence: an
unbounded computational repertoire from finite residency. A new
capability costs a new arrangement, never new machinery. The whole
road network of a serious workload fits hot in cache because nothing
in it brings substance — substance was installed once.

## Layer 4 — Circulation: the program leaves the loop

> "What if the trees live in the cache instead? Meaning compute can be
> made continually straight to and from that, not having to run it by
> the program etc before getting a new instruction?"

The program runs once, as a planter — it compiles the workload's trees
into the resident fabric and exits the steady state. Thereafter data
circulates: a datum routes into a resident tree and the whole tree
fires while values are in flight, each operation feeding the next in
place. Intermediates die in registers — never materialized, never
addressed, never returned to a control program between steps. The
"next instruction" is not fetched; it is wherever the result lands in
the tree, whose topology IS the control flow. The program reappears
only to pave novel shapes.

The economics this targets: on conventional cores the ceremony around
an operation (fetch, decode, schedule, move operands) costs 10-100x
the operation. Removing the program from the loop attacks the dominant
term, not the arithmetic.

## Layer 5 — Exits

> "And only the exits are sent."

Only exit values — results at a tree's boundary — ever cross any
boundary: cache to RAM, process to process, node to node. Intermediates
are unaddressable by construction. Exits are NAMED; a boundary crossing
degenerates to the name alone when the far side already holds the
value; a firing whose output name already exists is a pointer swap.

> "It could in theory just go through a matrix which matches the data
> structures or code to the predetermined results without actual
> computation. Just pointerswaps and done."

The result matrix is grown by occurrence, never emitted by prophecy:
first arrival of anything pays real computation once; recurrence rides
as lookup. Traffic becomes proportional to what was CONCLUDED, not
what was touched.

---

## The promises (what data must give to live in this machine)

1. **Immutable** — written once; sharing and residency are safe.
2. **Identity-carrying** — arrives named; lookup needs no hashing.
3. **Recurrence-visible** — repetition expressed as reference, never
   as repeated bytes.
4. **Mappable** — shape/topology explicit and stable, so trees can be
   laid onto real SRAM and tags can route.

The premise in one line: these four promises are why the machine
treats code royally and data poorly; a representation that makes all
four erases the caste system.

## The safety condition

Data-as-code is historically the vulnerability class of the century
(injection). This machine's data can only ever ARRANGE a fixed, vetted
vocabulary — it can never mean "execute arbitrary bytes." The fixed
vocabulary is not an implementation choice; it is the thing that makes
dissolving the code/data boundary survivable.

## Falsifiable claims (each with a sign the design predicts)

1. **Routing beats prediction where shape-entropy is high.** Tag-routed
   dispatch vs branchy dispatch over the same stream, swept from 2 to
   ~1000 interleaved shapes: crossover as predictor tables thrash,
   widening without bound. (The one prior test of shape-compiled firing
   ran at 2-3 shapes — where predictors are perfect — and lost; the
   claimed regime has never been measured.)
2. **Circulation beats program-mediated stepping.** Whole-tree fused
   firing vs one-operation-at-a-time with materialized intermediates:
   time, instructions, and energy.
3. **Exits-only collapses traffic.** Bytes crossing the core/memory and
   node/node boundaries, staged vs circulating: ratio ~ intermediates
   over exits.
4. **Arrangement-residency fits.** Resident bytes per shape; a
   ~1000-shape road network fits hot in L2 where equivalent branchy
   code plus predictor state cannot.
5. **Movement is energy** (from prior art, still open): fewer bytes
   must show as fewer joules on battery-powered hardware regardless of
   prefetch hiding.

## What would kill it

- Real workloads needing unbounded per-element VERBS (vocabulary grows
  until it is an instruction set again).
- Real-world recurrence and shape-entropy too low for the routed and
  memoized layers to pay.
- Claim 1 failing its sweep.
- The adoption problem: the engine must win one niche on measured
  advantage before any deeper layer (silicon cooperation) is reachable.
  Representations win software first; hardware bends afterward.

## The engine

One component at the silicon boundary IS the whole-stack agreement
(the JVM/V8/kernel pattern): it holds the vocabulary and road table
hot, receives tagged arrivals, routes into fired plans, hosts
circulation, emits only exits, paves unknown shapes through its single
slow walker, and converts the outside world's bytes exactly once at
the edge. It does not exist yet. The prior prototype's router is NOT
this engine and does not become it by renaming.
