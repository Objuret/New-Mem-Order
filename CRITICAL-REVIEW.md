# Critical Review — The Activation Model Prototype

Independent adversarial review of the whole build: spec, code, measurements,
and process. Commissioned as a hostile pass — *not a friend of this project*.
Conducted 2026-07-11 on branch `claude/build-it-r1yzg9` at commit `c99549d`
("18/18 harnesses pass end-to-end"), cross-checked against the second run on
`claude/new-session-uytd6w`.

Method: read every spec/brief/report/log; adversarial line-by-line code audit
of the runtime and all world-side passes; independent rerun of all 18
harnesses in a clean container; independent reconstruction of the phase-10
corpus and re-measurement against modern compressors; direct verification of
the most damaging claims against the committed evidence files. Where I say
"confirmed," I reproduced it myself; where I say "argued," it is analysis I
found credible but did not independently rerun.

---

## Verdict

**The engineering is real and unusually disciplined. The comparative claims
that make the project sound important are systematically inflated, and at least
one published table contradicts its own committed data in the model's favor.**

Two things are true at once and both must be said:

1. The prototype does what the low-level claims say: one byte string that is
   stored form = wire form = executed form, walked directly with no decode
   step; demanding = reading = firing; append-and-swap crash recovery with no
   recovery code; a universal library that genuinely stayed tiny across many
   workloads. The correctness gates (an independent C interpreter reproducing
   Python-written stores to a checksum; byte-identical world trees across
   languages) are stronger discipline than most research code. Deterministic
   numbers reproduce to the byte. The project also publishes many of its own
   losses. This is not a fraud.

2. Almost every *headline comparison* — "beats gzip 1.7×," "under the dedup
   floor," "0.86× of cat," "1.79 vs 2.68 crossings," "only 17% slower,"
   "~2.2× faster" — survives only under a favorable choice of baseline,
   metric definition, consumed unit, or (in one case) a number that does not
   match the file committed beside it. Corrected, the model is a
   *competitive-but-not-winning* dedup/CAS store with an interesting
   uniformity property, not the category-defining result the reports imply.

The gap between (1) and (2) is the review. The prototype is a good faith,
technically competent experiment wrapped in marketing it did not earn.

---

## Part I — Confirmed measurement problems (I reproduced these)

### 1. CRITICAL — Phase 16's published wall-time row contradicts its own committed JSON, in the model's favor, at the headline point

REPORT.md (phase 16 table) publishes single-core wall ratio (am/raw):

| p | 0% | 50% | 90% | 99% |
|---|----|-----|-----|-----|
| **published** | 1.07× | 1.16× | 1.17× | **1.17×** |
| **computed from `phase16-results.json`** (`am_s/raw_s`) | 1.10× | 1.18× | 1.17× | **1.52×** |

At p=99 the committed evidence says the walk is **52% slower**, not 17%. The
p=99 row appears to have been copied from the p=90 row. This is not rounding,
and it is the single number that would most damage the phase's story ("the
traffic win costs almost nothing in time"). REPORT.md line 845 explicitly
states the result JSONs "remain the original per-phase evidence," so this
cannot be excused as a later rerun overwriting the file — the table and the
JSON were committed together in `e85e5f1` and disagree. **This is the most
serious finding in the review:** a published result contradicting its own data
in the flattering direction. It must be corrected regardless of what else is
decided.

### 2. CRITICAL — Phase 10's storage win exists only against gzip; modern compressors beat the model ~6×, and on real disk blocks it loses to tar.gz

REPORT.md phase 10 headlines: store **4.60 MB** vs tar.gz 7.63 MB, "1.7×
smaller than tar.gz, and below the perfect whole-file-dedup floor (5.34 MB)…
the gzip rematch, on dedup's terrain: won."

I reconstructed the exact corpus (phase10.py is seeded, `random.Random(7)`) —
30.43 MB logical / 5.34 MB unique, matching the JSON — and ran the baselines
the phase never tried:

| form | size | vs model store |
|---|---|---|
| gzip -9 (the only baseline tested) | 7.63 MB | — |
| **model store (condensed+compacted)** | **4.60 MB** | 1.0× |
| `zstd -19 --long=27` | **0.76 MB** | **6.0× smaller than the model** |
| `xz -6` (defaults) | **0.74 MB** | **6.2× smaller than the model** |

The entire mechanism narration ("gzip cannot see a duplicate past its 32 KiB
window") is true of gzip *and only gzip*. Any long-window codec erases the
result. The "below the floor" rhetoric is also misleading: 5.34 MB is a floor
only for *whole-file* dedup — sub-file matching and ordinary compression both
legitimately go under it, so "lands under the floor" dresses up a
non-achievement as beating a bound.

The defense on record ("the compressed form remains per-file demandable, which
no archive is") is real but was never measured against the tools that share
that property — a content-addressed backup store (borg/restic) lands near
~1 MB *while keeping per-file access*, which would negate it.

**And the model's own committed data undercuts the byte claim.** `du()` records
both apparent bytes and 4 KiB-rounded block usage. `phase10-results.json →
store_final`:

```
raw:         4,598,469   ← the number reported
ext4_blocks: 18,362,368  ← actual disk, 4,130 tiny files
files:       4,130
```

On real disk the store occupies **18.4 MB** — 2.4× *worse* than the 7.63 MB
tar.gz it claims to beat, and 24× worse than `xz`. The comparison table's first
row is literally labelled "plain ext4" while the store row silently switches to
apparent bytes. The same apparent-vs-allocated substitution underlies phase 9's
"ext4 parity (−1.0%)" (raw 10.94 MB vs `ext4_blocks` 15.29 MB in the JSON) and
phases 3/6's "half of ext4."

### 3. HIGH — Phase 11's "0.86× of raw cat" baseline is not cat; ~80% of it is a checksum both sides pay

`native/amfire.c:206–210` folds every delivered byte through a loop-carried
`x = x*131 + b` and both the fire path (`:254`) and the "cat-equivalent" read
path (`:281`) run it. A serial per-byte multiply dominates a memory read, so
the "raw read" denominator is mostly arithmetic, not I/O — which compresses the
fire/read ratio toward 1.0 and manufactures the "nearly free" headline. The
benchmark auditor measured ~82% of the "cat" time as the fold on this host;
against an actual cheap consumer, warm firing is ~1.5× raw reading and several
times slower than real `cat`. The phase's **kill condition is narrated, not
coded** — there is no threshold or assert in phase11.py, so "the kill condition
did not trigger" is unfalsifiable as written. (Fidelity, by contrast, *is*
asserted — credit where due.) Cold numbers come from a single run and, tellingly,
**inverted on my rerun** (committed 0.42×; this container 1.05×), which is the
whole problem with publishing single-run wall times as findings.

---

## Part II — Argued measurement problems (auditor analysis, credible, not independently rerun)

### 4. CRITICAL (argued) — "Crossings per byte," the self-declared THE metric, is decided by a definitional exemption

Phase 13 charges the conventional server's `json.loads` of every wire line as a
crossing (phase13.py:120–121) but charges the model's router **zero** for the
exactly-equivalent receiver-side work: `fire()` walks the same instruction
bytes and materializes `bytes(buf[off:off+n])` copies of every literal — an
intermediate representation under the metric's own definition — yet construction
is charged "once," at the producer only. The auditor's accounting: charging the
model's ~1.0–1.1 MB of ingest-side decode symmetrically moves it from 1.79 to
≈3.4 crossings/byte — *above* the conventional indexed pipeline's 2.68. The sign
of the headline residual flips. A genuine defense exists (amx fires literals as
zero-copy slices) but phase 13 measured the *Python* router, which demonstrably
copies. As published, "who counts as a crossing" is what picks the winner.

### 5. HIGH (argued) — Phase 16/18's "raw" baseline is forbidden from doing what any real format would

At p=99, 99% of records are exact duplicates drawn from a fixed 64-entry
dictionary, but the raw baseline must inline the full 48-byte note every time
(membench.c:242–247). A conventional record with a 1-byte template id would be
~8 bytes — *smaller* than the model's ~10–12 — and would beat it on every axis.
The 0.29× bytes / 0.15× LL-miss result is interning/dictionary encoding, a
standard technique, measured against a baseline banned from using it. No sweep
of dictionary size ever stresses the L1-residency assumption the whole §0 story
depends on.

### 6. HIGH — Phase 18's time-domain "win" has no committed evidence and does not reproduce at the claimed magnitude

There is no `phase18.py` and no `phase18-results.json`; `hwbench-results.json`
is gitignored. The claims "1.9× from uniform-width sids," "walk-bound
0.41–0.46×," Pixel "all-cores 0.85×," and the summary "~2.2× faster" rest on
zero committed artifacts, and the Pixel numbers were produced by the owner on
his own phone with no recorded methodology. On rerun the *direction* is real
(uniform sids help; the model wins the walk-bound kernel at p=99) but the
magnitude was ~1.5×, not ~2.2×, with raw-mode times varying ±35% run to run.
A machine-specific best-case number from an unrecorded run is stated as the
model's general truth, and no variance is reported anywhere in the project.

---

## Part III — Confirmed code / claim contradictions

### 7. CRITICAL — "Malformed input is unexpressible / the parsing-bug class has nothing to exist for" is false, and there are undisclosed crash paths

This is a load-bearing §0 claim (a security claim), and the code contradicts it
line for line:

- `instruction.py` `fire()`/`skip()` **are a hand-written TLV parser** with the
  full classic repertoire of validation errors: "not an instruction (tag N)",
  "truncated literal", "truncated reference", "unknown structure id". The
  parsing-bug class does not have "nothing to exist for" — it was reimplemented.
  One parser instead of thousands is a real, defensible win (the protobuf/Cap'n
  Proto argument), but it is a *deduplicated* parser, not a *deleted* one.
- **Undisclosed crash paths** (confirmed by rerun):
  - A demand reference containing a NUL byte reaches `os.path.isfile` and raises
    `ValueError: embedded null byte`, which is not a `Refusal`; the router's
    `except Refusal` misses it and the connection task dies. (The FUSE layer
    checks for NUL; the router's demand path does not — inconsistent.)
  - A **well-formed** but deeply nested instruction (legal, therefore the
    "unexpressible" defense does not apply) overflows the recursive `fire()`/
    `skip()` past the 50k recursion limit and raises `RecursionError`, uncaught
    → the network-facing framing path crashes instead of refusing. A remote
    party can hand-craft a legal instruction that is a trivial DoS.
  - A corrupt/short head renders to fewer than five fields and
    `layer.py:160`'s `rendered.split(b"\n")[:5]` unpack raises an uncaught
    `ValueError`, crashing the FUSE op instead of returning EIO.

  Garbage bytes and path traversal, by contrast, *are* handled robustly
  (traversal defense uses realpath containment and defeats even in-world
  symlink escapes) — so the claim is not uniformly wrong, but "always fires or
  refuses" is not true.

### 8. MAJOR — The FUSE metadata path is a parse-and-deserialize layer of exactly the kind the brief forbids

`layer.py:160`: `t, chain, size, mtime, mode = rendered.split(b"\n")[:5]`
followed by `int(size)`, `int(mtime)`, `int(mode)`. That is splitting a byte
record into fields and deserializing ASCII to integers — a parser plus a
deserializer producing a 5-tuple second representation, which the build brief's
hard rules list as "do not reintroduce." It is disclosed only as a benign
"record convention," never as the parsing/serialization violation it is.

### 9. MAJOR — "Crash consistency by construction, zero recovery code" rests on write atomicity the code does not have, and is tested against a scenario that cannot fail it

- `emit-disk` is `open(path,"wb"); f.write(content)` — truncate-then-write,
  **not atomic**. `rename` uses atomic `os.replace`, but head *writes* do not.
  The whole "head is emitted last, so an interrupted write leaves the old head"
  argument depends on the head write being atomic; a crash *during* the head
  write leaves a torn head → finding #7's corruption on remount.
- **Nothing ever fsyncs.** `fsync`/`flush` are documented no-ops; the native
  engines have no `msync` either. So "survives restart" means "survives a
  process kill with the page cache and disk intact," which is what phase 3's
  SIGKILL test exercises (it kills *between* operations). Power loss — the
  failure class recovery code exists for — is never tested, and the test as
  designed cannot exercise a torn write. The rhetoric ("crash consistency with
  no code") overreaches to a guarantee the prototype does not provide.
- `shapemine.py:186` **abandons append-and-swap entirely**, overwriting stored
  instruction files in place (disclosed as forced by literal-reference
  opacity). A crash mid-pass leaves a half-rewritten instruction that every
  holder of its literal reference then renders as garbage — and unlike the live
  layer there is no old-head fallback, because the reference being overwritten
  *is* the identity.

### 10. MAJOR — The headline "structure count" stays flat only because the growing tier was renamed and dropped from it

The spec's own §6 rule: "relocating capability from library to grammar does not
shrink the true number." The project honors that for grammar nodes and then
does precisely the forbidden move one level over: the universal tier is
advertised as flat (11, "did not move at 25× the volume"), while the tier that
actually grows with the data — 1,506 promoted templates in phase 10, plus
promoted shapes — is relabelled "store-local" and excluded from the headline.
Meanwhile the shape/template promotion in `condense.py`/`shapemine.py`
**creates new resident structures from workload data at pass time**, which is
in tension with A1's "nothing can create structures at runtime" (defended by
relocating "runtime" to "between mounts"). The refined claim the project
eventually states — *universal tier stays flat while templates track content* —
is honest and interesting. The flat headline number oversells it.

### 11. MAJOR — Deletions that reappear elsewhere

- **Dictionary/version negotiation** (§4, "deleted by A1 because the set is
  frozen") returns in `sync.py`: a receiver that refuses "unknown structure id
  N" must be shipped `lib/` files and restarted. That is version-matching by
  refusal. The frozen-set premise that licensed the deletion is the same one
  finding #10 shows is not actually frozen.
- **A second representation / a store** (§0, "never let a second representation
  come into existence"; brief, "no store/index component") returns as
  `layer.py`'s render cache — a persistent map of fully materialized file
  contents keyed by chain ref, mutable runtime state outside any terminal, on
  by default. Disclosed (DECISIONS 1.15, FRICTION #28) with a reasonable
  soundness argument, but the rule it violates was stated absolutely.

---

## Part IV — Where the complexity actually went (the honest ledger the reports gesture at)

The model's purity is real but *subsidized*, and the subsidy is the interesting
result, not the purity:

- **Storage was rented, not deleted.** "No store component" delegates
  allocation, naming, lookup, and durability to the filesystem — itself a
  database. The project admits this (FRICTION #48, the sharpest thing in the
  repo) only after phase 14, and only under external challenge. The win held at
  file granularity (phases 9–12) and collapsed at record granularity (phase 14:
  ~7–20× behind), which is exactly where the rent falls due. amx (phase 17)
  fixes it by *re-importing a small allocator* — i.e., building the store
  component back.
- **Control flow, loops, time, uniqueness, coordination, and all mutation were
  exported to "the world."** Phase 15 is candid: this is "a decision-and-
  rendering engine with world-side control flow, not a computer." The pump that
  drives it is ordinary imperative code. The brief's "no escape hatch into
  ordinary code for the workload logic" is honored in the letter (the *ops* are
  instructions) and not the spirit (the *control* is Python).
- **Formats died at one layer and regrew one layer up.** No parse-error
  repertoire at the instruction layer (true, and unusual) — but content
  immediately regrew micro-formats (line-terminated records, `"] user: "`
  markers, decimal-ASCII numbers, five-field heads), and with them in-band
  injection: the spoofability findings (#9, #32) are the classic vulnerability
  shape returning. The model deletes format *multiplicity* and *negotiation*,
  not format-ness — a real but much smaller claim than §0's.
- **Concurrency.** "Nothing is written, so simultaneity is free" holds inside
  the model because the single-router-terminal rule is a global write lock
  (REFLECTION.md admits this), and the accepted lost-update window means
  contended posts silently orphan data — ruled "open by design," which is a
  legitimate choice but is the opposite of "simultaneity is free."

---

## Part V — Process and hygiene

- **Pace and self-certification.** 18 phases in three days (phases 5–8 across a
  ten-minute window), every result generated and verified by the same builder,
  no adversarial baseline in the loop until this review. The correctness gates
  are genuinely good; the *comparative* baselines are the predictable blind spot
  of a solo builder marking their own homework, and that is exactly where the
  problems cluster.
- **Reproducibility is real but not turn-key.** All 18 harnesses pass here and
  deterministic numbers match to the byte — a genuine strength. But `fusepy`
  does not pip-install on stock Ubuntu 24.04 (had to be hand-placed), so a naive
  rerun silently skips the five FUSE phases, and "reproduce with `python3
  phase3_tests.py`" overstates how self-contained it is.
- **No variance anywhere.** Wall-time and throughput claims are min-of-3–5 or
  single-run with no dispersion, on a virtualized host, yet several are stated
  as findings (phase 11 warm/cold, phase 18 "~2.2×"). At least one (phase 11
  cold) inverts on a second machine.
- **Evidence gaps.** Phase 18's headline rests on gitignored/absent artifacts
  (#6). Phase 17 narrates "ranges over three same-day runs"; the JSON has one.
  Phase 16's Pixel paragraph has no artifact at all.
- **Repo hygiene.** `worldB/` binary test fixtures are tracked *and* listed in
  `.gitignore`; the default branch (`master`) has no commits; the two run
  branches share no common ancestor. Minor, but symptomatic of the fast pace.
- **Documentation-to-code honesty is, genuinely, high.** Most structural
  weaknesses (rented store, second-class references, render-over-fields,
  lost-update, gzip-loses-on-unique-content) are disclosed in FRICTION/
  DECISIONS/REFLECTION with real intellectual honesty. The failure is not
  concealment; it is that the *top-line summaries* consistently round toward the
  flattering reading while the honest caveats sit three files deep. Finding #1
  (the phase-16 table) is the one place that crosses from "flattering framing"
  into "contradicts the evidence."

---

## Severity summary

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | Phase 16 wall table (1.17×) contradicts JSON (1.52×) at p=99 | Critical | Confirmed |
| 2 | Phase 10 storage win is gzip-only; loses 6× to zstd/xz; loses to tar.gz on real disk blocks | Critical | Confirmed |
| 3 | Phase 11 "0.86× of cat" baseline is ~80% checksum; kill condition not coded | High | Confirmed |
| 4 | "Crossings/byte" flips sign under decode-symmetric accounting | Critical | Argued |
| 5 | Phase 16/18 raw baseline banned from dictionary encoding | High | Argued |
| 6 | Phase 18 time win: no committed evidence, ~1.5× not ~2.2× on rerun | High | Confirmed (no artifact) |
| 7 | "Malformed input unexpressible" false; 3 undisclosed crash/DoS paths | Critical | Confirmed |
| 8 | FUSE metadata path is a forbidden parse+deserialize layer | Major | Confirmed |
| 9 | Crash-consistency claim rests on absent write atomicity + no fsync | Major | Confirmed |
| 10 | Headline structure count flat only by excluding the growing tier | Major | Confirmed |
| 11 | Dictionary-negotiation and a store/second-representation reappear | Major | Confirmed |

---

## What the project should claim instead (the defensible version)

Strip the marketing and there is a real, modest, interesting result:

- A single self-delimiting encoding that is simultaneously stored, wire, and
  executable form, walked directly with no decode-to-tree in the hot path —
  **demonstrated, with an independent second interpreter as proof.** This is the
  genuine novelty and it holds.
- A content-addressed dedup store whose compressed form stays per-file
  addressable, **competitive with (not superior to) modern compressors**, and
  whose real differentiator is addressability, not ratio — which the reports
  themselves identify in REFLECTION §7 and then bury.
- A universal combinator library that stayed remarkably small (≤11) across a
  message board, a POSIX filesystem hosting real git, ledgers, and merges — a
  real echo of the syscall-count prior, **honestly counted only if the
  data-derived template tier is counted with it.**
- A traffic/cache-miss reduction from dictionary encoding that is real and
  deterministic, **converts to wall-time only under contended bandwidth**, and
  is measured against a baseline that should be allowed to intern too.

That is a good systems experiment. It is not "the conversion-and-movement
category deleted," and every place the reports say or imply the latter is a
place a hostile reader stops trusting the former.
