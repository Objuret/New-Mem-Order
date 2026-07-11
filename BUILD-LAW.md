# BUILD-LAW — enforcement by construction, not by promise

Twenty builds by two independent agents produced the same failure: the
builder's scaffolding (managers, queues, batching apparatus, computed
identity, flattened edges) silently replaced the machine, and the
scaffolding's losses were reported as the machine's. Confessions
followed every time; prevention never did. Conclusion, taken from the
machine's own design principle: discipline does not hold —
**unexpressibility holds**. The vocabulary didn't promise not to eval;
eval was made unexpressible. Building works the same way from now on.

## Law 0 — the only law that matters

**No measurement may be reported, recorded, or even summarized in chat
as a result "of the machine" while any gate below fails.** A number
produced under a failing gate is a measurement of scaffolding. Publishing
it as the machine's is the one act this branch exists to prevent. If a
gate cannot pass on 2026 silicon, the honest output is "unmeasurable
here, because <gate>", never a number.

## The gates

Each gate is a property of the machine (MACHINE.md layer in brackets)
paired with a MECHANICAL check. "Mechanical" means: a script asserts
it; no agent's judgment, no reviewer's diligence, no promise.

**G1 — No manager. [Layer 4]**
The path from arrival to road entry is one indirect dispatch. There is
no receiving layer, no queue, no scheduler, no delivery callback —
nothing for administration to live in.
CHECK: fabric source contains no queue/buffer/callback constructs
(lint list, maintained in the checker); measured instruction count
from edge handoff to road entry ≤ a stated constant, asserted in the
harness.

**G2 — Per-arrival, order untouched. [Layers 1–2]**
Processing order is arrival order. No reordering apparatus exists, so
no order-reconstruction metadata exists. If locality batching is used
in the emulation shell, it is invisible: order preserved, exits
untouched.
CHECK: exits carry name + value and nothing else (byte-budget assert);
zero provenance/sequence fields anywhere in the fabric.

**G3 — Identity is carried, never computed. [Layer 5, the lookup rule]**
Names are assigned exactly once, at the edge, at birth. The fabric
never hashes, scans, or compares content to discover what something is.
CHECK: hashing/equality-scan calls are lint-banned from fabric
sources; allowed only in edge modules.

**G4 — Circulation is real. [Layer 4]**
Trees feed trees inside residence. A multi-stage computation crosses
no boundary between stages; intermediates are never addressed,
allocated, or serialized.
CHECK: allocator hook asserts zero heap allocation in the steady-state
firing path; no intermediate ever appears in an exit stream.

**G5 — The edge preserves shape. [Layer 1; v0's flattening failure]**
The edge may not reduce reality's structure to make routing easy. The
argument structure of real events survives into tags. Any claim about
real traffic's shape-richness reports the tag-stream entropy measured
BEFORE and AFTER edge conversion, side by side.
CHECK: the harness computes and prints both entropies; a "too few
shapes" conclusion with a collapsed after-entropy and a rich
before-entropy is an automatic gate failure.

**G6 — Two ledgers, structurally separated. [The emulation rule]**
Every silicon compromise lives in edge/emulation modules only, each
named in EMULATION.md with its measured cost. Fabric modules cannot
import emulation modules — the dependency direction makes
contamination unbuildable. Every reported measurement states both
accounts: the machine's (inside the fabric) and the emulation's (the
shell), separately, always.
CHECK: import/include direction asserted by the checker; the harness
output format has two labeled columns or it does not run.

## Enforcement

A `lawcheck` script implementing every CHECK above must exist before
the first line of engine code, and every measurement harness runs it
first and refuses (nonzero exit, no output tables) on any failure.
The checker is part of the build, versioned with it, and extended
whenever a new scaffolding species is discovered — the lint lists are
expected to grow the way the corrections in DERIVATION.md grew.

## Why this document exists

MACHINE.md says what the machine is. DERIVATION.md and SOUL.md say how
its builders failed to hear it. Neither prevented the next failure,
because both address the agent's judgment, and under build pressure
the agent's judgment is precisely what substitutes conventional
technique for the concept — reliably, across independent agents, while
sincerely intending not to. This document therefore removes the
judgment from the loop: the wrong build must fail to compile, fail to
run, or fail to report — before any human has to call bullshit.
