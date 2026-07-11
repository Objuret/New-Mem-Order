# OPEN DECISIONS — options written, nothing implemented (working rule 2)

Status as of 2026-07-11, after claim 1 PASSED its sweep. Each item
below is a structural silence in MACHINE.md. Options and a
recommendation are given; **no option is being built until Jocke
rules.** Rulings can be one line each ("1b, 2a, 3a, 4 yes").

## 1. Order of the remaining falsifiable claims

Claim 1 is measured (PASS, regime-bound — see
`claims/claim-1-shape-entropy/`). Remaining:

- **(a) Claim 2 next — circulation beats program-mediated stepping.**
  Whole-tree fused firing vs one-op-at-a-time with materialized
  intermediates. Attacks the 10-100x ceremony number, the heart of
  layer 4, and its apparatus grows directly out of claim 1's firing
  plans (extend plans from straight-line op sequences to trees).
- **(b) Claim 3 next — exits-only collapses traffic.** Needs trees
  with interior/boundary distinction; naturally builds ON claim 2's
  apparatus, awkward before it.
- **(c) Claim 4 next — arrangement-residency fits.** A footprint
  accounting (resident bytes per shape vs branchy code + predictor
  state); cheap, but its sharpest form also wants real trees.
- Claim 5 (energy) is blocked on Jocke's phone regardless.

**Recommendation: (a) then (b) then (c)** — each apparatus feeds the
next, and together they leave behind most of the engine's firing core.

## 2. Engine host form

MACHINE.md: "one component at the silicon boundary IS the whole-stack
agreement." Silent on what the component concretely is.

- **(a) An embeddable runtime (C library):** vocabulary, road table,
  walker, circulation, exits as a library a process links. Closest to
  the silicon boundary, cheapest to measure honestly, no IPC noise in
  the numbers. Does not yet LOOK like the JVM/V8 pattern.
- **(b) A resident daemon owning the fabric;** clients hand it tagged
  streams over shared memory. Matches the whole-stack-agreement
  pattern visibly, but every measurement now contains IPC/transport,
  and the engine's own economics get harder to isolate.
- **(c) A compiler + runtime pair** (programs are planted ahead of
  time, engine only executes). Purest reading of "the program runs
  once, as a planter," but forces language-design decisions long
  before any measured advantage exists.

**Recommendation: (a),** structured so (b) can wrap it unchanged once
the core wins measurements — the JVM itself began embeddable.

## 3. First niche (the kill-list demands one measured win)

- **(a) Tagged event-stream / message-bus processing.** Claim 1's PASS
  is literally this regime: many interleaved message kinds, high
  shape-entropy, per-message work small. The measured 1.4-2x is the
  entry wedge.
- **(b) Telemetry/log pipelines** (movement-dominated, recurrence-heavy;
  exits-only shines) — but claims 3/5 unmeasured, so the wedge is
  currently narrative, not numbers.
- **(c) Replication / materialized views** (pointer-swap layer shines) —
  same status as (b).

**Recommendation: (a)** — it is the only niche where this branch
already holds a measured advantage.

## 4. The Layer-2 tag formalization (INTERPRETATION flag)

MACHINE.md's layer 2 (tag-forks vs value-forks; tags on the surface;
routing = one indexed lookup) is still marked INTERPRETATION —
formalized by an assistant, accepted in conversation, never explicitly
ratified. The engine's routing surface hardens this into API. **Needs
a yes / a correction from Jocke before the engine fixes it in code.**

## 5. Claim-1 follow-ups (cheap, optional, not started)

- Rerun on bare metal with a PMU for the branch-miss accounting
  (harness already reads counters when they exist).
- A shape-frequency sweep between uniform and 99%-skew to map exactly
  where the crossover between predictor-territory and
  routing-territory sits.
