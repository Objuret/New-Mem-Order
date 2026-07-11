# Response to the External Review (2026-07-11)

`CRITICAL-REVIEW.md` (branch `claude/critical-build-review-42kzhx`) is an
adversarial audit of this build at commit `c99549d`. This document is the
builder's disposition of every finding: what was verified, what was fixed,
what is corrected on the record, and the little that is contested. The
review's core charge — *honest engineering, inflated headlines* — is
accepted. Corrections live in REPORT.md's ERRATA section; code fixes are in
this commit; each item below links the two.

The review is also the strongest §6-style falsification event this project
has had, and it is logged as FRICTION #56. Every prior phase was graded by
the same person who built it; the first hostile grader found real errors
within hours. That is a finding about process, recorded as such.

## Dispositions

| # | Finding | Disposition |
|---|---|---|
| 1 | Phase-16 table contradicts its own JSON (1.17× vs 1.52× at p=99) | **CONFIRMED — corrected.** Verified against `e85e5f1`: the JSON says 1.52×. The table was transcribed from an earlier run's console output; the evidence file came from a later rerun; they were committed together unchecked. Table now recomputed from the committed JSON; erratum states the wrong number, the right one, and the cause. Same-day reruns land 1.16–1.20×, which is now reported as dispersion, not silently substituted. |
| 2 | Phase-10 win is gzip-only; xz/zstd ~6× smaller; on-disk blocks lose to tar.gz | **CONFIRMED — corrected.** Independently reverified on a rebuilt corpus: `xz -6` = 0.74 MB vs the store's 4.60 MB apparent / 18.7 MB in ext4 blocks (4,130 files). "Beats gzip 1.7×" is retracted as a general compression claim and restated as what it was: a demonstration that reference-based storage sees recurrence a 32 KiB window cannot. "Under the dedup floor" is retracted (sub-file matching legitimately goes under a whole-file floor). The store's honest differentiator — per-file demandability of a deduplicated form — stands but is now stated *with* the ratio loss, and the borg/restic comparison the defense requires is logged as open and unmeasured. Apparent-vs-blocks substitutions in phases 3/6/9/10 are all flagged in the erratum. |
| 3 | Phase-11 "0.86× of cat" baseline is mostly checksum; kill condition never coded | **CONFIRMED — corrected.** The baseline runs the same per-byte fold as the fire path, so the denominator is arithmetic-dominated; the claim is restated as "0.86× of a raw-read-plus-identical-fold reference," explicitly not `cat`. The uncoded kill condition and the single-run cold number (which inverted on the reviewer's rerun) are noted in the erratum. |
| 4 | Crossings/byte flips sign under decode-symmetric accounting | **ACCEPTED as definitional dependence — both accountings now published.** Under "materialized second representations" accounting the model scores 1.79; under strict "any intermediate copy" accounting the Python router's literal copies are chargeable and the reviewer's ≈3.4 estimate plausibly flips the sign vs conv-indexed (2.68). The structural claim narrows to what survives both: the model never re-encodes at rest and never parses into a second object model; whether walk-copies count is an engine property — amx fires literals as zero-copy slices and would not pay them — and an amx-based remeasure is logged as open work, not assumed. |
| 5 | Raw baseline forbidden from dictionary encoding | **ACCEPTED as scoping.** Phase 16/18 measure "a format that can reference its own recurrence vs one that cannot." A conventional schema with interned notes would get the same traffic win; the model's claim is that interning falls out of the single representation instead of a bespoke schema, not that convention cannot intern. Scope note added; dictionary-size sweep logged as open. |
| 6 | Phase-18 win: no committed artifacts, ~1.5× not ~2.2× on rerun | **ACCEPTED — artifact committed, variance stated.** `phase18-results.json` (this machine, this commit) is now in the tree; the erratum states magnitude is machine-dependent (0.44–0.69× across same-day runs on this VM — direction stable, magnitude noisy exactly as the review said; reviewer's container ~0.65×; Pixel single-core 1.45×, all-cores 0.85×), that raw-mode times vary ±35% on virtualized hosts, and that the Pixel figures are owner-run via `hwbench.py` on stock Termux with no independent observer. The direction (uniform sids help; the walk-bound kernel wins at p=99) reproduced everywhere it was tried, including by the reviewer. |
| 7 | "Malformed input unexpressible" false; NUL/recursion/short-head crash paths | **CONFIRMED — fixed in code this commit.** NUL bytes are refused in `resolve_ref`; legal-but-absurd nesting is refused (`RecursionError` → error frame at both framing and firing, router survives); a corrupt/short head returns EIO through the layer instead of crashing the FUSE op. New `robustness_tests.py` pins all of it plus garbage and traversal. The claim is rewritten to the defensible form the review itself offers: **one deduplicated parser, not a deleted parser class** — `fire()`/`skip()` are the system's single TLV walker, with a real refusal repertoire. |
| 8 | FUSE head record is a parse+deserialize layer | **CONFIRMED — acknowledged on the record.** DECISIONS 1.9 disclosed it as a convention; the review is right that `split()` + `int()` over a five-field record is materially the thing the brief's hard rules forbid, one layer up. Recorded as a standing violation-shaped tension (like FRICTION #9's markers), not explained away. Restructuring heads as per-field chains is noted as the model-pure alternative, unbuilt. |
| 9 | Crash-consistency claim rests on absent atomicity; nothing fsyncs; SIGKILL test can't catch torn writes | **CONFIRMED — partially fixed, claim scoped.** `emit-disk` now writes tmp-then-`os.replace`, so a torn write can never leave half a file at a reference (the old head genuinely survives mid-write crashes now). What is NOT fixed and now stated plainly: nothing fsyncs, so power-loss durability is not provided or claimed; the native engines still truncate named files in place (listed debt); `shapemine`'s in-place rewrite remains the disclosed exception. The claim is scoped to process-crash consistency. |
| 10 | Structure count flat only by excluding the growing tier | **ACCEPTED — headlines restated.** Every top-line "library stayed at 11" now reads as the two-tier fact: universal tier flat at 11 across all workloads; data-derived template/shape tier grows with content (1,506 templates in phase 10) and is A1-resident between passes. The A1 tension ("nothing creates structures at runtime" vs pass-time promotion) stays flagged for Jocke's §A1 clarification, which has been an open DECISIONS question since phase 3. |
| 11 | Dictionary negotiation and a second representation reappear | **ACKNOWLEDGED.** Refusal-driven lib shipping is version negotiation in refusal clothing; the render cache is a disclosed, default-on second representation with a soundness argument (DECISIONS 1.15). Both were disclosed at depth; the absolutes in the §0/§4 rhetoric overreach them. Spec language is Jocke's to amend; flagged. |

## Process items accepted

- **Variance:** wall-time findings will carry dispersion or ranges from here
  on; single-run walls stop being findings (phase-11 cold is the example the
  review caught inverting).
- **Reproducibility:** README now states the fusepy hand-install requirement
  (PHASE3-STATE.md recipe) instead of implying turn-key FUSE.
- **Self-grading:** the correctness gates were strong; the comparative
  baselines were the solo-builder blind spot. The review is the missing
  adversarial baseline, and this response is the mechanism working late but
  working.

## What is NOT conceded

- The one-representation core (stored = wire = executed, walked in place,
  independent C interpreter reproducing Python-written stores byte-for-byte)
  — the review itself confirms it.
- The universal-tier result as *scoped above* — 11 combinators covering a
  board, a POSIX filesystem hosting git, ledgers, merges, and a sequential
  program is the experiment's genuine §6 answer.
- The direction of the phase-18 memory-path result; magnitude is
  machine-dependent and now stated as such.
- Honesty of intent: the review found the deep caveats already written in
  FRICTION/DECISIONS/REFLECTION. The failure was rounding toward the
  flattering reading in summaries — real, corrected — not concealment.
