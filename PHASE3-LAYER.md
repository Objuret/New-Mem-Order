# PHASE 3 — THE LAYER

Complete instructions. This file is self-contained and authoritative for this phase; where it is silent, `activation-model.md` (the spec) rules; where both are silent, follow the decision protocol in §9. Do not come back to Jocke for anything pre-ruled here.

## 1. What this phase is

The runtime stops being a standalone system and becomes a transparent layer between unmodified programs and storage. Programs read and write ordinary files; underneath, every file is stored as an instruction chain over the resident structure library, and reading a file FIRES its chain to render the bytes. This tests the concept against real software instead of hand-written workloads: the condensation question (§6 of the spec) is now measured on content nobody wrote for us.

## 2. Carried state and rulings (closed — do not reopen)

- Phase 1+2 runtime carries over: instruction grammar (literal, composition, demand, error), router, library (concat, emit-disk, select, tally, last), files-as-unsent-instructions. Build on it, do not rebuild it.
- DECISIONS §2.1 (lost-update window): stays open by design. Irrelevant here anyway — see §5 concurrency ruling.
- All standing rules apply: no second representation of anything, nothing that fires values ever enters the library, model-wins-until-it-demonstrably-can't (friction log, not workaround), falsification is a SUCCESS state (stop, report, done).

## 3. Deliverable

A FUSE filesystem in Python (`fusepy`; if unavailable, `pyfuse3`) mounted at a normal directory, backed entirely by the runtime, passing the acceptance tests in §10, plus the measurements in §11.

**Environment fallback (pre-ruled):** if FUSE cannot mount in the build environment (no fuse device, no permissions), do NOT simulate a filesystem inside the report and do NOT abandon the phase. Build the identical layer behind a plain function API (open/read/write/readdir/unlink/rename/stat as Python calls), plus a harness that exercises it with the same operation sequences the acceptance tests would generate (including a scripted git-like workload: many small files, renames, content reuse). State prominently in REPORT.md that the FUSE binding itself is untested. The layer logic, condensation, and all measurements proceed identically.

## 4. Storage mapping (pre-ruled)

- **A file** = a head reference (one small file in the backing store at a stable path derived from the file's path) whose content is a literal node holding the reference to the file's current chain, plus metadata values (§6).
- **File content** = an instruction chain. Content that condenses is compositions over library structures; content that doesn't is literal nodes. Never store raw bytes outside literal nodes.
- **Chunking**: files larger than 64 KiB are stored as a composition of ≤64 KiB pieces (each piece a literal or a condensed composition). Chunk boundaries are content-independent (fixed size) in v1; note in FRICTION.md if fixed boundaries visibly hurt dedup.
- **Read** = demand the head, fire the chain, return rendered bytes. Offset reads render the chain and slice; log the cost. No caching in v1 (see §8).
- **Write** (any offset) = render current content if needed, splice the change, store the new chain, swap the head. Nothing is overwritten; the old head value is superseded but its chain remains. This is append+swap, the phase-1 pattern.
- **Delete** = remove the head reference. Chains become unreachable; do NOT build reclamation in this phase (space is a measurement, not a problem to solve).
- **Rename** = move the head reference.
- **Directories** = directories of head references in the backing store. A plain directory listing IS readdir. If you feel the need for any index, manifest, or database beyond this: STOP condition (§12).

## 5. Concurrency (pre-ruled)

One mount process = one router = the single owner of all terminals over the backing store. This satisfies the spec's terminal-binding rule by construction. Serve FUSE requests on the router's single loop; firings never yield (phase-1 property), so per-operation atomicity is free. Do not add threads, locks, or a second router.

## 6. Metadata (pre-ruled)

POSIX attributes programs need (size, mtime, mode) are stored as values inside the head instruction. Size = size of the rendered form (compute on write, store as value; never re-render just to stat). Permissions: store the mode bits, enforce nothing. Symlinks: store target as a value, readlink renders it. Hardlinks: NOT supported — return EPERM, log it. Timestamps beyond mtime: fake with mtime, log it. Every syscall faked rather than expressed natively goes in FRICTION.md with one line of why.

## 7. Condensation (the experiment)

Two stages, strictly ordered:

**Stage 1 — correctness first.** Everything stores as literal chains (chunked). Pass the acceptance tests this way. Overhead will be terrible; that's expected and irrelevant at this stage.

**Stage 2 — offline condensation pass.** A separate command that scans all stored chains, finds recurring content shapes, and rewrites chains to reference promoted structures. Rules:

- **Admission**: a candidate is promoted to a library structure only if it recurs in ≥3 distinct files. Prefer FAT candidates: the largest chunk of content/work that still recurs — never atoms. A recurring 4 KiB block beats a recurring 16-byte string; a recurring composition shape beats both.
- **Nothing that fires values.** Promoted structures are content templates and pure transforms only.
- **Every admission AND rejection logged** in LIBRARY.md with the hit evidence (which files, how many hits, bytes saved).
- **Re-running the pass must be idempotent** — rewriting a chain that already references promoted structures changes nothing.
- The pass writes new chains and swaps heads (append+swap, as everything). It must leave every file byte-identical when rendered — verify with checksums over the full tree before/after, automatically, in the pass itself.

Inline (write-time) condensation: NOT in this phase. Log the idea if it itches.

## 8. Performance (pre-ruled)

Correctness only. No caches, no memoization, no indexes in v1 — including the identity-cache the spec licenses; it stays unbuilt this phase so measurements show the raw model. Slow is a measurement, not a bug. The single exception: rendered-size stored as metadata (§6), because stat-storms would otherwise make git unusably slow rather than measurably slow.

## 9. Decision protocol

Pre-ruled above: environment fallback, chunk size, offset writes, metadata faking, hardlinks, admission threshold, no reclamation, no caching, no inline condensation, single router. For anything genuinely outside all of this AND outside the spec: write options + recommendation to DECISIONS.md, STOP the session. Never implement the recommendation. Do not stretch this protocol to avoid work that is merely tedious.

## 10. Acceptance tests (all must pass, in order)

1. **Byte fidelity**: write files of sizes 0, 1, 4095, 4096, 4097, 200 KiB, 5 MiB (random and text); read back byte-identical; overwrite ranges at offsets including chunk boundaries; read back byte-identical. Rename, delete, recreate.
2. **Real program**: `git init`, `git add`, `git commit` (×3 commits with edits), `git log`, `git checkout` of an earlier commit — all inside the mount (or the harness equivalent under §3 fallback), byte-correct, exit codes clean.
3. **Restart survival**: kill the mount process, remount, everything above still reads correctly. Zero recovery code permitted — if remount needs repair logic, that's a finding (STOP condition territory), not something to write.
4. **Condensation fidelity**: full-tree checksums identical before and after the condensation pass.

## 11. Measurements (REPORT.md)

1. Backing-store bytes vs. the same tree on plain ext4 — before condensation, after condensation. Report honestly if condensation loses.
2. Dedup evidence: the LIBRARY.md admission log with bytes-saved per structure.
3. **The headline: structure count over content volume** — the growth/flattening curve, now measured on real content. Carry the curve forward: 2 (phase 1) → 5 (phase 2) → N (this phase).
4. Firings per syscall for read/write/stat/readdir at the acceptance-test workload.
5. FRICTION.md appended: every faked syscall, every place the model fought, every place convention predicted pain that didn't come.

## 12. Stop conditions (stop, DECISIONS.md, report — success state)

- Any index/database/manifest needed beyond directories of head references (queue-becomes-store).
- Any second representation of anything, anywhere, including "just for the wire/FUSE boundary."
- Any candidate structure that would fire values.
- Remount requiring recovery/repair logic.
- Acceptance test 2 impossible without violating any of the above.

## 13. Session continuity

This phase spans multiple sessions. Maintain `PHASE3-STATE.md` at repo root: what's done (checklist mirroring §10/§11), current blocker if any, next action. First act of every session: read it. Last act: update it. Never re-plan the phase inside a session — this file is the plan.
