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

---

# Phase 5 — the wire (2026-07-09)

Transfer-is-activation, tested between two routers for the first time.
Node A: the phase-4 world (board, ledgers, promoted shapes). Node B: an
empty world, universal library only. No wire protocol was designed —
the stored form is the wire form (spec §8), so replication is emits
carrying opaque instruction files as values, over the same client
framing phase 1 built. Reproduce: `python3 phase4.py --no-log` then
`python3 phase5.py`; raw numbers in `phase5-results.json`.

## What happened

1. **Content without the dictionary**: B stored all 25 files (1,025
   wire bytes) but firing a condensed chain refused: `unknown structure
   id 101`. The error grammar node plus condensed traffic IS a
   bootstrap protocol nobody wrote — the refusal names exactly what the
   receiver lacks.
2. **84 bytes of library shipped**, B's router reloaded, and **all 26
   phase-4 query results fired on B byte-identical to A** — sums,
   sorts, averages, joins, board reads, natively, with no format, no
   negotiation, no import step.
3. **Incremental sync**: one new post on A, mtime-selected delta of 2
   files, **163 wire bytes** — heads and deltas, as the spec predicts
   traffic should look. The new message was uncondensed (posts spell
   their shape out until a pass sees them) and interoperated with the
   condensed corpus with no reload.

## Honest numbers

Minimal JSON of the same logical data is 346 bytes — SMALLER than the
full sync's 1,025 wire bytes at this toy scale, where per-file emit
wrappers and references dominate tiny files. Recorded as-is
(FRICTION.md #27). What the model buys here is not the full-sync byte
count: it is the 163-byte delta, and everything that never had to
exist — schema, parser, version handshake, import pipeline. Whether
shared residence wins on raw bytes at scale is unmeasured until a
bigger corpus.

## New open questions (DECISIONS.md)

§2.2: may a router make a structure resident at first reference instead
of at start? (Dictionary delivery is currently restart-priced; the lazy
reading is the natural A4 move but touches A1 — recommendation written,
NOT implemented, awaiting ruling.) §2.3: remote references — noted,
never needed, undesigned.

---

# Phase 6 — compaction and the render cache (2026-07-09)

Phase 3 deliberately measured the raw model and left its two costs
standing: 24.5× store growth from superseded history, and 32 firings
per read syscall from whole-chain renders. Phase 6 builds the two
answers those findings pointed at and prices them on the phase-3 store.
Reproduce: `python3 phase3_tests.py` then `python3 phase6.py`; numbers
in `phase6-results.json`.

## Compaction (`am/compact.py`)

**268.9 MB → 5.7 MB** — 4,390 unreachable chain files deleted, 126 live
files render-verified before and after. There is no GC machinery to
describe: the heads directory is the root set, the demand graph inside
the chains is the reachability structure, and deletion is `os.remove`.
Combined with condensation, the store now rests at roughly **half** the
plain-ext4 size of the same logical tree, with zero unreachable bytes.

## The render cache (layer-side, `--raw` to disable)

Same workload (full stat storm + reading every file, twice), raw vs
cached, checksums asserted identical:

| | read calls | firings | firings/read | wall time |
|---|---|---|---|---|
| raw (v1 baseline) | 495 | 15,050 | 30.4 | 4.39 s |
| cached | 495 | 1,404 | **2.84** | **1.42 s** |

The residual 2.84 is the head demand every operation pays — heads are
the one mutable indirection, are never cached, and are therefore the
model's cost floor for identity-over-time (FRICTION.md #29). Cache
invalidation had literally nothing to do: a write stores a fresh chain
reference, which is a natural miss; the overwrite test passes against
the warm cache and a cold raw remount alike. The cache is honestly a
demander-side memory, not the spec's below-demand identity cache — the
distinction and its soundness argument are in DECISIONS.md 1.15.

phase3_tests.py pins `--raw`, so every previously published number
remains the raw model.

---

# Phase 7 — multi-writer: merge is a query (2026-07-09)

Two nodes, two writers, zero coordination. Alice writes only on A, bob
only on B — one writer per head, so §2.1's window never opens between
writers. Sync exchanges chains (each node ships only what its writer
owns); the merged thread is never stored: it is `sort∘concat` over both
demanded chains, fired at read time. Determinism makes both nodes'
merges byte-identical — convergence by construction, no conflict
resolver, because nothing was ever contended. Derived views (newest-2,
one user's posts) are further compositions over the merge, held by
readers, resting nowhere. Unsynced nodes diverge honestly (the world
differs across a demand boundary) and reconverge on re-sync with no
repair step.

**Zero new structures, zero grammar changes.** One real finding: naive
bidirectional sync reopened the lost-update window at the copy layer
(a stale foreign head clobbered a fresh one) — cured by extending write
ownership to shipping, not by coordination (FRICTION.md #31, DECISIONS
1.16). Reproduce: `python3 phase7.py`; results in
`phase7-results.json`.

---

# Phase 8 — open-key grouping: shape, not machinery (2026-07-09)

The last standing falsification pressure from phase 2 (#10): group
posts by user when nobody knows the user set. Keys inside rendered
content are unreachable without a resident parser, which stays refused.
The model's answer, predicted by FRICTION #8 and now demonstrated: the
WRITER stores the projection. The post firing appends the author to a
projection chain — a fourth emit in the same indivisible firing — and
the unknown key set becomes a query: `uniq(sort(demand(authors)))`.
Grouping then composes exactly as phase 2 did, with keys the demander
just learned; a never-before-seen poster is discovered by the same
query. One new structure (`uniq`, a pure adjacent-dedup fold; universal
tier 10 → 11), zero index components: the projection is ordinary
content — demandable, replicable, condensable, compactable, owned by
its writer. The honest cost is the one every database pays: projections
must be written at write time; conjuring one later is a world-side
backfill. Reproduce: `python3 phase8.py`.

---

# Phase 9 — scale on real content (2026-07-09)

The "is it actually working and relevant" test: 637 files / 11.0 MB of
real Python-stdlib source through the whole pipeline — ingest via the
FUSE mount, condense, compact, cold-remount verification, replication
to a second node, delta-sync after edits. `phase9-results.json` has the
raw numbers; `python3 phase9.py` reproduces.

**What held:** byte-identical fidelity end to end; **the universal tier
did not move (11 → 11) at 25× the previous volume** — the §6 claim's
strongest evidence yet; usable prototype throughput (6.7 MB/s ingest,
7.6 MB/s read-back, 4.7 s condensation, sub-second full replication);
store at ext4 parity (−1.0%) after passes; a never-touched pipeline
composition (condense → compact → sync) ran clean.

**What got corrected:** the compression rhetoric. Real single-version
source has little ≥512 B cross-file recurrence — 13 templates, 158.8 kB
saved — and gzip beats the uncompressed-literal wire 4× (2.56 MB tar.gz
vs 10.99 MB). The model's storage wins are dedup-shaped (versions,
copies, boilerplate, templates), never entropy-shaped; §7's
degrades-gracefully clause performed exactly as written, and §0's
"everything stays small" now carries that qualifier in this report.
Edit deltas re-ship whole files (153 kB for three small appends) — the
literal-reference opacity cost (#15), priced at the wire. FRICTION
#36–#38.

---

# Phase 10 — the recurrence-shaped corpus (2026-07-09)

Phase 9's honest loss (gzip 4× better on unique content) demanded the
rematch on the corpus shape the model's compression story is about:
version history. Eight snapshot generations of an evolving source tree
— the backup workload — 1,228 files, 30.4 MB logical, 5.3 MB unique.
Reproduce: `python3 phase10.py`; numbers in `phase10-results.json`.

| form | MB | ×logical |
|---|---|---|
| plain ext4 | 30.43 | 1.00 |
| tar.gz (labeled anecdote) | 7.63 | 0.25 |
| **store, condensed+compacted** | **4.60** | **0.15** |
| wire, full replication | 4.71 | 0.15 |
| unique-content floor (perfect whole-file dedup) | 5.34 | 0.18 |

**The model beats gzip 1.7× on this terrain and lands under the
whole-file-dedup floor** — gzip cannot see a duplicate past its 32 KiB
window, condensation dedups by reference across the whole store, and
recurring blocks inside *modified* files dedup as well (1,506 templates,
13.6 s pass, fidelity verified by cold-remount checksum). The phase ran
entirely on phase-3/6 machinery; the universal tier stayed at 11.

Together with phase 9 the compression claim is now scoped honestly in
both directions: unique snapshots → entropy coding wins; recurring
content (versions, backups, copies — most of the world's stored bytes)
→ reference-sharing wins, and the compressed form remains per-file
demandable, which no archive is. FRICTION #39–#40.

---

# Phase 11 — the native fire loop (2026-07-09)

Every prior phase measured speed's determinants; this one measures
speed. `native/amfire.c` (~300 lines of C) realizes the grammar's read
path per spec §8 — byte-compatible with every stored world, templates
resident at start. Kill condition, stated in advance: if native firing
can't approach raw-read throughput, the conversions the model deleted
were cheaper than the interpretation it added. Benchmarked on the
phase-10 store (4.6 MB of chains serving 30.4 MB of content) vs raw
reads of the plain corpus. Reproduce: `python3 phase11.py`.

| | fire (deliver 30.4 MB) | raw read (`cat`-equivalent) | ratio |
|---|---|---|---|
| warm | 412 MB/s | 479 MB/s | **0.86×** |
| cold | 84 MB/s | 199 MB/s | 0.42× |

**The kill condition did not trigger.** Warm, interpretation costs 14%
over raw reading — while the firing path reads 6.6× fewer bytes from
disk (the store is 0.15× the content). Fidelity is proved the strong
way: an independent C interpreter fired stores written by Python and
every rendered byte checksum-matched the plain corpus. Cold is the new
honest cost: reference-chasing opens ~4× more small files, so
latency-limited media pay (FRICTION #41) — bandwidth-limited media
win. Python-speed folklore corrected while we're at it: direct Python
render is 85 MB/s (native = 5×); the earlier 5–8 MB/s was FUSE
round-trips (#42).

§0's argument now has numbers on every clause: the deleted machinery
never ran (phases 1–10), the added interpretation is nearly free
(this phase), and the byte movement saved is 6.6× on recurring content
(phase 10).

---

# Phase 12 — the tool (2026-07-09)

The product turn: `am.tool`, a snapshot/replication CLI — the job
phase 10 proved the model wins on merit. ~250 lines of world-side
composition over chartered machinery; zero new structures, zero grammar
or rule changes. Exercised end to end by `phase12.py`:

- four snapshots of an evolving 2.2 MB source tree; every generation
  restores and verifies byte-identical; history browses as directories
  through a FUSE mount (`g1/ g2/ g3/ g4/`);
- store holds 3 generations (6.7 MB logical) in 2.52 MB (0.38×);
- replication to a second store: 2.55 MB full, then **0.16 MB delta**
  for the next generation — the #37 delta problem answered by workflow
  ordering (snap → condense → compact → push) rather than rule changes;
- the replica needs no import step and no format: it is a store.

Dogfood findings (FRICTION #44): the ≥3-file admission threshold makes
dedup warm up one snapshot late (kept as charter law; a 2-file
threshold awaits a ruling), and deltas are chunk-grained rather than
edit-grained — #15's last costume.

---

# Phase 13 — THE metric: the same job, three designs (2026-07-09)

One identical job — 10,000 records over a socket into durable storage,
then 10 aggregate queries, answers asserted identical — implemented
three ways: the canonical JSON log+scan service, the same service with
an ingest-time index (per-user amounts files — the exact analogue of
the model's write-side projection, so design matches design), and the
model. Accounting is mechanical byte counts, charged evenly — the
model's in-flight renders are counted with no discount. Reproduce:
`python3 phase13.py`.

| per payload byte | conv log+scan | conv indexed | model |
|---|---|---|---|
| **crossings (re-representation)** | **14.15** | **2.68** | **1.79** |
| copies (socket + disk) | 15.62 | 4.02 | 3.27 |

Wall-time rows exist in the harness output but are NOT comparable —
they race a pure-Python fire loop against C-accelerated `json`
(phase 11 holds the native evidence: firing at 0.86× of `cat`).
Crossings and copies are byte counts, identical whatever language the
converter is written in.

**The honest decomposition of the headline:** 7.9× against the naive
design collapses to **1.5× against the best conventional design** —
most of the naive gap was the projection, which any competent stack can
add. The 1.5× residual is the pure one-representation dividend, and its
anatomy is exact: the indexed conventional pipeline still pays two full
crossings of the payload that the model structurally cannot pay —
encode-at-birth (object → JSON) and decode-at-ingest (JSON → object) —
because its stored form and its usable form are different things. The
model's floor is 1.0 (information becomes an instruction once) plus the
rendered projection per query; measured 1.79. Both sides then pay their
projections about equally. §0's claim, measured at its most
conservative: **the conversion tax the architecture itself forces is
~2.7 crossings per byte conventionally versus ~1.8 here — the deleted
category is real, and it is worth about a third of the best
conventional pipeline's byte-touching, or 5× of the naive one people
actually ship.**

---

# Phase 14 — the real build: amd and true benchmarks (2026-07-09)

`native/amd.c` (~550 lines): the complete §8 realization for everything
benchmarked — full grammar, all 11 universal structures, the emit
terminal, resident templates, the phase-1 wire protocol, one event
loop. Gates before any timing: **identical ingest through the Python
router and through amd leaves byte-identical world trees**; answers
identical across all four pipelines; refusal parity. Reproduce:
`python3 phase14.py`.

| seconds (10k records, 10 queries) | conv log | conv idx | model py | **model amd** |
|---|---|---|---|---|
| construction (pre-built, timed apart) | 0.038 | 0.038 | 0.117 | 0.117 |
| ingest | 0.293 | 0.394 | 4.803 | **2.992** |
| queries | 0.324 | 0.005 | 1.695 | **0.113** |

**What the true clocks settle:** the interpreter gap is closed (queries
15× faster native; phase 13's wall caveat retired). What remains is not
representation — phase 13's crossings stand at 2.68 vs 1.79 — but
LAYOUT: one instruction per file means two file creates per record at
ingest (20k creates = disk-bound 3.0 s vs one appended log at 0.3 s)
and 2,000 opens per query (0.113 s vs one-file projection at 0.005 s).
The same IOPS wall as phase 11's cold reads. File-granular workloads
(phases 9–12) never felt it; record-granular work is ~7× behind the
best conventional design because of it. The fix is packing (references
naming into containers) — a genuine structural question, escalated with
a recommendation to DECISIONS §2.4, not implemented.

## Reproducing

```
python3 demo.py           # phases 1-2: board + queries
python3 report.py         # phase 1-2 measurements from the run
python3 phase3_tests.py   # phase 3: FUSE mount, four acceptance tests
python3 phase4.py         # phase 4: ledger workload + shape condensation
python3 phase5.py         # phase 5: two routers, replication, bootstrap
python3 phase6.py         # phase 6: compaction + render cache pricing
python3 phase7.py         # phase 7: two writers, merge-as-query, convergence
python3 phase8.py         # phase 8: open-key grouping via write-side projection
python3 phase9.py         # phase 9: 11 MB real-corpus scale run
python3 phase10.py        # phase 10: 8-generation snapshot corpus rematch
python3 phase11.py        # phase 11: native fire loop vs cat, warm and cold
python3 phase12.py        # phase 12: the am.tool workflow end to end
python3 phase13.py        # phase 13: the end-to-end pipeline head-to-head
python3 phase14.py        # phase 14: amd (native router) + true benchmarks
```
