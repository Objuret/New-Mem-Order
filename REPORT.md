# Prototype Report — Message Board on the Activation Model

Answers the brief's four measurements and the spec's §6 question. Two
phases: phase 1 (the message board) and phase 2 (computation pressure:
queries over the phase-1 data). Numbers are from the demo run of
2026-07-08 (`python3 demo.py`, then `python3 report.py` to regenerate —
timestamps and ids will differ, shapes and counts will not). Phase-1
sections are kept as written; phase 2 is appended at the end with the
growth curve.

## What ran

A message board: one thread, two users (alice, bob), three posts and two
full reads through a single router, one refused read of a nonexistent
thread, one router restart in the middle. All workload logic is
instructions over the library; the client only constructs instructions
and displays outputs. The board survived the restart bit-for-bit with no
persistence code anywhere — the unsent instruction files under `world/`
are the only state that exists.

The shape the model gave the board: a message is an unsent instruction
`concat(demand(previous), ...fields)`; a thread head is a literal node
holding the newest message's reference at a fixed path; reading the
thread is demanding the head's value, which fires the entire chain —
reading is running, and the rendered thread is the output of the oldest
message's firing cascading forward. Posting is one indivisible firing
that emits the new message file and replaces the head file.

## Measurement 1 — structure count (the §6 number)

**2 library structures + 4 grammar nodes = 6.**

| | |
|---|---|
| `concat` | pure |
| `emit-disk` | terminal (the only side effect in the system) |
| literal, composition, demand, error | grammar nodes, counted per §6 |

Full log with forcing reasons: LIBRARY.md. Notable: no read structure
exists (demand covers persistence), no socket-send was forced (the
demand return path covers replies), and nothing that fires values was
needed — no §6 falsification event occurred.

## Measurement 2 — repetition

From `stats.log` (26 instruction firings = 13 wire arrivals + 13
demanded files):

- **distinct composition shapes: 4** across 26 firings, 98 grammar-node
  evaluations
- shapes: `D` (bare demand, ×9), `L` (head/genesis files, ×7),
  `C1(D,L,L,L,L,L,L,L)` (message files, ×6), `C1(C2(L,L),C2(L,L))`
  (post/new-thread, ×4)

Every operation the board performs — create, post, read, and even the
stored message files themselves — collapsed onto four shapes. The
post instruction and the new-thread instruction turned out to be the
same shape. This is the repetition §6 predicts, at toy scale.

## Measurement 3 — stored-form overhead

Grammar overhead of stored instructions over their content bytes
(content = literal payloads + demand references):

| stored instruction | file bytes | content bytes | overhead |
|---|---|---|---|
| message (typical, ~40-char text) | 104–108 | 85–89 | 19 |
| genesis | 25 | 23 | 2 |
| thread head | 26 | 24 | 2 |
| **whole world after demo** | **338** | **277** | **61 (18.0%)** |

Overhead is ~2 bytes per node (tag + length varint); a message costs a
flat 19 bytes of grammar regardless of text length, most of it the
per-field literal framing. No compression codec exists anywhere — the
compactness is references replacing repeated content (each message
carries the whole thread-so-far as a 20-odd-byte demand reference).

## Measurement 4 — friction

Full log: FRICTION.md. Two honest model edges (two-step reads through a
mutable-world indirection; a lost-update window on contended posts —
options for Jocke in DECISIONS.md §2.1), two habit-vs-model findings
(`concat` moonlighting as a sequencer; explicit genesis instead of
empty-as-absence), one engineering note (chain depth = recursion depth),
and a list of things that produced zero friction where convention
predicted plenty: no converters, no recovery code, no locks, no parse
errors.

## §6 verdict, honestly scoped

For this workload the claim held with room to spare: the library
saturated at two structures almost immediately and every subsequent
operation reused them. Values in flight did not balloon; the structure
set did not balloon. But this is one tiny workload chosen to be
model-friendly — the encouraging number is how early the library stopped
growing, not the absolute 6. The next falsification pressure should come
from a workload that wants computation (filtering, counting, comparing),
which `concat` cannot absorb.

---

# Phase 2 — computation pressure (2026-07-08)

The question ruled for this phase: how much does the library grow when a
workload demands computation `concat` cannot absorb? Three queries over
the existing board data, run in the demo *after* the router restart, so
they provably operate on nothing but the surviving files:

- **(a) find** posts containing a given value → `select(chain, "\n", needle)`
- **(b) count** posts per user → `concat` of one `tally(chain, "\n", "] user: ")` per user, the result table composed inside the instruction
- **(c) N newest** posts → `last(chain, "\n", N)`

Every condition — needle, delimiter, count — entered as a value, a
comparison operand. Nothing filter/fold-shaped ever needed to fire a
sub-instruction; the eval boundary was never approached. **No §6
falsification event.**

## The growth curve (measurement 1, updated)

| after | library | grammar | total |
|---|---|---|---|
| phase 1 | 2 (1 pure + 1 terminal) | 4 | 6 |
| phase 2 | 5 (4 pure + 1 terminal) | 4 | **9** |

Growth was +3, exactly one structure per query shape (filter, fold,
positional take), all pure. The ~10-structure reporting threshold was
not crossed, though 9 is close enough to note: each genuinely new
*computation shape* seems to cost one structure. The counter-observation
is that all three took the same operand form (value, delimiter,
condition) and composed with the existing library on first contact — the
`count` result table is plain `concat` over `tally` outputs.

## Repetition (measurement 2, updated)

Full demo including phase 2: **62 instruction firings, 7 distinct
composition shapes**, 305 grammar-node evaluations. New shapes:
`C3(D,L,L)` (find, ×2), `C5(D,L,L)` (newest), and the one-firing
per-user table `C1(L,C4(D,L,L),L, ×3 users)`. Message-file firings rose
from 6 to 24 — the per-user count re-demands the chain once per tally,
because the grammar is a tree with no way to bind a value once
(FRICTION.md #13).

## Stored-form overhead (measurement 3, unchanged)

Queries left the world byte-identical: 338 stored bytes, 18.0% grammar
overhead, exactly as after phase 1. A query is an instruction that
borrows the chain's firing and vanishes — no index, no cache, no
materialized view came into existence.

## Friction (measurement 4)

Six new entries, FRICTION.md #8–#13. The central finding (#8): the
stored chain fires to one thing only — the rendered thread — so queries
compute over the render and inherit its convention (spoofable markers,
#9). The model never needed a parser, but field-precise querying would
require a different *stored* chain shape, not more query machinery.
Secondary findings: open-key grouping would need a resident parser
(refused, demander supplies the keys, #10); computation forced a shared
number convention, decimal ASCII (#11); and the tree-not-DAG cost above
(#13).

## §6 verdict after phase 2

The claim still stands, with its first real price tags visible. The
library grew linearly with new computation shapes (not with data, users,
or queries run), conditions-as-values held everywhere, and querying
added zero resident or resting state. The pressure that phase 2 exposes
for a phase 3 is: field-precise access (stored-shape evolution),
open-key grouping, and whether shape-per-computation growth flattens
into reuse as workloads accumulate — the §6 bet is that it does.

---

# Phase 3 — the layer (2026-07-08)

Per PHASE3-LAYER.md: the runtime became a transparent FUSE filesystem —
unmodified programs above, instruction chains below, reading fires the
chain. **FUSE mounted for real in this environment** (no §3 fallback):
all four acceptance tests ran against a genuine kernel mount, and
acceptance 2 is real git, unmodified. Raw numbers: `phase3-results.json`
(committed); reproduce with `python3 phase3_tests.py`.

## Acceptance (§10) — all four pass, in order

1. **Byte fidelity**: sizes 0 / 1 / 4095 / 4096 / 4097 / 200 KiB / 5 MiB
   (random and text), range overwrites on and across 64 KiB chunk
   boundaries, extension past EOF, truncate shorter and longer, rename,
   delete, recreate, symlinks — byte-identical throughout.
2. **Real git**: init, add, 3 commits with edits/additions/deletions,
   log, checkout of the first commit (content verified against v1) and
   back, `git fsck --strict` clean. Lock files, index renames, and
   reflog appends all behaved.
3. **Restart survival**: mount process SIGKILLed, remounted; all 126
   paths byte-identical, git log and fsck clean. **Zero recovery code
   exists.** Crash consistency is structural: a write's emits fire
   left-to-right inside one indivisible firing with the head last, so an
   interrupted write leaves the old head naming the old complete chain.
4. **Condensation fidelity**: full-tree checksums identical through a
   fresh mount after the pass; a second pass rewrote nothing
   (idempotent).

## Measurement 1 — backing store vs plain ext4

| | bytes |
|---|---|
| logical tree on plain ext4 (mirror, raw) | 10,996,255 |
| store, **reachable**, before condensation | 11,012,495 (+0.15%) |
| store, **reachable**, after condensation | **5,682,464 (−48.3% vs ext4)** |
| store, total incl. superseded chains | 268,891,322 (24.5×) |

Two honest numbers, reported separately. Reachable: the stored form
costs 0.15% over raw before condensation and **half of ext4 after** —
references replacing repeated content, no codec anywhere. Total: 24.5×,
because every write re-stores whole content and nothing is reclaimed
(charter: space is a measurement) — see FRICTION.md #15 for why the
live layer cannot reuse a previous version's chunks (literal-reference
opacity), the phase's central cost finding.

## Measurement 2 — dedup evidence

Admission log in LIBRARY.md. Five templates admitted: a 546 B text
block recurring 9,801 times across 5 files (5.35 MB saved), the shared
license header as two blocks (1068 B + 631 B × 30 source files each),
one more text block, and the docs boilerplate (663 B × 3). Zero
two-file rejections; **80 occurrences span-rejected on fixed 64 KiB
boundaries** — the charter's fixed-boundary caveat, confirmed and
logged (FRICTION.md #16).

## Measurement 3 — the headline growth curve

**2 (phase 1) → 5 (phase 2) → 10 (phase 3)**, grammar constant at 4.

The ~10-structure reporting threshold is hit exactly — a finding, per
charter. Its texture matters: the 5 new structures are data-derived
content templates, store-local rather than universal, discovered by the
pass rather than designed. The library now has two tiers — 5 universal
computational structures + N-per-store promoted templates — and the §6
question refines to: does the UNIVERSAL tier stay flat while the
store-local tier tracks content? This phase's answer: the universal
tier needed zero additions to host a filesystem and run git.

## Measurement 4 — firings per syscall (acceptance workload)

| op | calls | firings/call | | op | calls | firings/call |
|---|---|---|---|---|---|---|
| getattr | 13,745 | 0.68 | | truncate | 4 | 5.50 |
| read | 807 | 32.27 | | utimens | 9 | 3.00 |
| write | 288 | 17.48 | | readlink | 3 | 4.00 |
| create | 172 | 1.00 | | readdir | 159 | **0** |
| rename | 74 | **0** | | unlink/mkdir/rmdir | 102 | **0** |

Namespace operations fire nothing — they are reference management in
the world. getattr is one head firing (0 for directories); the stored
rendered-size metadata did its job (stat never renders). read's 32.3 is
the no-caching price: every ≤128 KiB kernel read fires the whole chain
(FRICTION.md #18) — the raw model, as the charter wanted measured.

## Measurement 5 — friction

FRICTION.md #15–#21. Central: write amplification from literal-ref
opacity (#15); boundary span-rejections (#16); the faked-syscall list
(#17); whole-chain renders per read (#18); the head's record convention
as phase-2's #8 recurring at the metadata level (#19); idempotency
forcing boundary-stable rewrites (#20). And the zero-friction list
(#21) is the phase's quiet headline: unmodified git on a firing-pattern
filesystem, crash consistency with no code, no locks under a real
kernel's concurrency, and an optimizer whose correctness check is one
checksum comparison because rendering is deterministic.

## Verdict after phase 3

The claim survived contact with real software. Universal structures:
still 5 — a filesystem and git needed none added. Condensation on real
content beat ext4 by 2× on reachable bytes with a 5-template library.
The honest debits are operational, and both were pre-priced by the
charter: unreclaimed history at 24.5×, and render-per-read at 32
firings/syscall — the first is what condensation-as-compaction and the
licensed-but-unbuilt identity cache exist to answer, in some later
phase, if Jocke rules them in.

---

# Phase 4 — computation pressure + shape condensation (2026-07-09)

The question phase 2 left open: does the universal tier grow linearly
with computation (the §6 balloon) or converge? Workload: an expense
ledger over the board world — totals, extremes, averages, sorted
listings, threshold filters, remaining-budget across two chains — every
operation parameter a value, nothing fold-shaped firing a
sub-instruction. Raw numbers: `phase4-results.json`; reproduce with
`python3 phase4.py`.

## The answer: sub-linear, for the first time

**5 structures in, 8 computations composed out.** Forced additions:
`sum`, `sort`, `div`, `sub`, `pick` (universal tier 5 → 10 — arithmetic
atoms and one reorder, exactly the ALU-plus-order kit). NOT added, because
composition covered them: max and min (`last∘sort`), average
(`div∘(sum,tally)`), plain count, count-over-threshold (`tally∘pick`),
top-N, per-user board search, and the join-shape (remaining budget =
`sub` across two demanded chains — relational join for enumerable keys
is demander-side composition, no structure). Full table in LIBRARY.md.
This is the SQL-style convergence the phase existed to test for:
computation cost atoms, not combinations.

Refusals compose too: average-of-empty-ledger propagates "division by
zero" from three compositions deep; numeric sort over text refuses. The
workload contains zero error-handling code.

## Shape condensation: arrival is now recognition

The graph-built-interpreter idea, made model-pure: `am/shapemine.py`
mines stored instructions for recurring composition shapes (≥3 distinct
files, admitted only if net stored bytes saved > 0) and promotes them as
resident structures — bodies with per-instance constants folded in and
varying positions as VALUE slots (demands stay outside as ordinary
operands; nothing fires values, no computed references). Two shapes
admitted on the first corpus: the message shape (×3 instances) and the
ledger-entry shape (×9). Twelve instances rewrote from spelled-out trees
to shape-reference + operands; stored instruction bytes 609 → 542
(−11%); everything byte-identical through a router reload; second pass
admits and rewrites nothing.

A rewritten message file's shape is no longer discovered by walking —
it arrives as a structure ID resolved by table lookup. Recurring
structure migrated from the traffic into the residence, which is §0's
compression argument applied to form instead of content.

## Growth curve

**Universal: 2 → 5 → 5 → 10. Store-local: 0 → 0 → 5 templates → +2 shapes.
Grammar: 4, unchanged through all four phases.**

The two tiers now have three phases of separated evidence: universal
growth tracks new computation *kinds* and went sub-linear the moment
composition had enough atoms; store-local growth tracks content and pays
for itself by construction (admission requires net bytes saved).

## Friction

FRICTION.md #22–#24: constant folding is corpus-relative (three
same-minute posts folded the timestamp into the shape — admission
quality scales with corpus size); in-place rewrite is forced for
interior chain nodes because their references are baked into downstream
demand nodes (supersede-by-new-ref only works at heads); and the
zero-friction list — composition, composed refusals, and
recognition-on-arrival — is the phase's actual result.

## Reproducing

```
python3 demo.py           # phases 1-2: board + queries
python3 report.py         # phase 1-2 measurements from the run
python3 phase3_tests.py   # phase 3: FUSE mount, four acceptance tests
python3 phase4.py         # phase 4: ledger workload + shape condensation
```
