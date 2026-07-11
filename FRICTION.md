# Friction Log

Every place the model fought back while building the message board
(build-brief, Measurements #4). Each entry: what happened, why, and a
verdict — model flaw, habit flaw, or honest model edge.

## 1. Reading a thread takes two demands

The thread head is a mutable-world indirection: a file at a fixed path
whose content is the reference of the newest message. A reader demands
the head (getting a reference as a value), then demands that reference.
It cannot be one instruction, because a demand reference must be a held
literal — the output of the first demand can never be wired into a second
demand node (spec §2, Demand node).

**Verdict: honest model edge, mild.** The two steps are two crossings of
a demand boundary, and the spec says the world may change between them.
The cost is one extra round trip, not a lost capability.

## 2. Posting has a lost-update window

Posting is (a) demand the head to learn the newest message reference,
then (b) fire one instruction that stores the new message (chained to
that reference) and replaces the head. (b) is atomic — fires-whole on the
single router that owns the terminal. But (a)→(b) spans a demand
boundary: if two clients interleave, the second head replacement wins and
the first message is orphaned (still on disk, no longer reachable from
the head).

Closing the window inside one firing would need either a computed demand
reference (forbidden) or a structure that constructs instruction bytes
around a demanded value (not in the spec; edges toward laundering
computed references into stored literals). Neither was implemented.

**Verdict: honest model edge, real.** This is the model's concurrency
story meeting read-modify-write for the first time. Options for Jocke in
DECISIONS.md. Note the failure mode is mild by construction: nothing is
corrupted, no torn state exists — a message becomes unreachable, because
nothing was ever written over.

## 3. `concat` is doing double duty as a sequencer

A post must put two `emit-disk` firings inside one indivisible
instruction. The only way to make two children of one composition is to
give them a parent structure, and the only parent available was `concat`
— so a post is "concatenate the two emit outputs" where the concatenation
result is discarded. It works (operands fire within the whole), but the
intent is sequencing, not joining.

**Verdict: habit flaw, probably.** The model may simply not distinguish
"do these together" from "combine these"; a composition IS togetherness.
Kept `concat` rather than growing the library with a `seq`.

## 4. Uniqueness must come from the world

Message references need to be unique; nothing inside the model can mint
uniqueness (no randomness, no clock in structures — spec §7). Clients
supply timestamp-based ids. Two clients posting in the same millisecond
under the same name would collide.

**Verdict: honest model edge, as designed.** The discipline held; the
burden moved to the world, which is where the spec says it lives.

## 5. The empty thread is a thing, not an absence

A message chain must terminate, so a thread starts as a genesis message
(a plain literal) plus a head naming it. "Create thread" therefore exists
as an operation that stores two files. Convention would have let an empty
thread be the absence of rows; the model made emptiness explicit.

**Verdict: habit flaw.** Explicit genesis is arguably cleaner: demand of
a nonexistent thread refuses instead of returning an empty page.

## 6. Deep threads = deep recursion

A thread of N messages is N nested demand firings; the prototype's
recursive `fire()` consumes a Python stack frame per level (recursion
limit raised to 50k). Engineering, not model: an iterative walker would
delete the limit. Also note firing the head renders the WHOLE thread —
pagination would be a different chain shape, not a smarter reader.

**Verdict: engineering note, plus a real observation:** the chain shape
couples "read the thread" to "fire all of it."

## 7. What produced zero friction in phase 1 (worth recording)

- Wire format == file format == executable form held with no converters
  anywhere. The encoder in `am/instruction.py` is the only constructor.
- Restart survival required zero code. No warmup, no recovery, no replay:
  the files ARE the state, and nothing else ever held any.
- The response path fell out of "an output is itself an instruction":
  the router returns a literal node or an error node, and the client
  receives it with the same framing that everything else uses.
- No locks anywhere, and no race hunt was ever needed inside the runtime:
  firings never yield, so the terminal's atomicity was free, exactly as
  the spec predicted.
- Malformed input genuinely had nothing to exist for: the only failure
  modes on the wire are truncation (wait for more bytes) and a bad tag
  (refuse the stream) — there is no "parse error" repertoire.

---

# Phase 2 — computation pressure (2026-07-08)

## 8. Queries run over the rendered value, not the stored fields

A stored message holds its fields as distinct literals, but its only
firing renders them into one value; an instruction's executable form is
single-purpose, and there is no second way to fire the same bytes.
Queries therefore compute over the in-flight rendered thread and depend
on its rendering convention (line-terminated records, "] user: "
markers) — a de-facto format inside a value. Two mitigations kept this
inside the model: the convention enters query instructions as VALUES
supplied by the demander (who asked for that rendering when it posted),
so the library stays convention-free; and the rendered form exists only
in flight (A2) — it is regenerated per query from the single stored
representation, so no second representation ever rests anywhere.

**Verdict: honest model edge, and the phase's central finding.** The
model did not need a parser, but it paid for that by querying through
the render. A workload wanting field-precise queries would push toward a
different *stored* chain shape (fields demandable separately), not
toward query machinery.

## 9. Rendered-form queries are spoofable

Because conditions match patterns inside the rendered value, a post
whose text contains "] alice: " inflates alice's tally and pollutes
find results. The fields were distinct at rest; the conflation happens
in the executable form (consequence of #8).

**Verdict: model edge consequence.** Today's equivalent is grepping a
log; the model reproduced that ceiling exactly.

## 10. "Per user" required the world to hold the user set

`tally` counts one needle per firing. Grouping by an unknown key set
would need key-extraction between format markers — a resident parser,
and the library ballooning §6 warns about. Refused: the demander
supplies the users it asks about, the same burden as holding references
(spec §7).

**Verdict: honest model edge.** Enumerable-key workloads fit; open-key
grouping is future falsification pressure.

## 11. Numbers needed a byte form

`tally` emits and `last` consumes decimal ASCII. Values are bytes; the
moment computation produced a count, the library needed a shared number
rendering — the smallest possible type convention crept in as content.

**Verdict: unavoidable under A2; logged because it is convention shared
by structures**, which is exactly the kind of thing that must stay
counted (it is capability the receiver must already hold).

## 12. Segment semantics had to be pinned

"Delimiter is a terminator, not a separator" (trailing "\n" does not
create an empty segment). Deterministic, but an arbitrary choice made in
the library rather than by the workload.

**Verdict: engineering wrinkle** — the price of delimiter-as-value.

## 13. The grammar is a tree, not a DAG

The per-user count fires one `tally` per user, and each tally must
demand the chain again — there is no way to bind a demanded value once
and wire it to several operands. Message-file firings went from 6
(phase 1 demo) to 24 (with queries) mostly from this. Purity makes the
re-firing harmless and cacheable-by-identity (spec §4), but the
instruction cannot express the sharing.

**Verdict: honest model edge.** A let/bind grammar node would be a spec
amendment; at prototype scale it is a non-problem (speed is out of
scope), so it is recorded here rather than raised as a decision.

## 14. What produced zero friction in phase 2

- No filter or fold ever needed its condition to be a fired
  sub-instruction; needles, delimiters, and counts all rode as values.
  The eval/apply boundary was never even approached — no §6
  falsification event.
- Queries leave zero residue: nothing was stored, no index appeared, no
  cache had to be managed. A query is an instruction that borrows the
  chain's firing and vanishes.
- The three new structures composed with everything existing on first
  contact: `count`'s result table is `concat` over `tally` outputs with
  literal row labels — no glue machinery.

---

# Phase 3 — the layer (2026-07-08)

## 15. Writes cannot reuse the previous version's chunks

Every write re-stores the file's whole content as fresh chunk files.
The chunk references live only inside the stored chain, which the live
layer may not parse (reading stored bytes structurally would be a
second interpretation of the executable form); carrying the chunk list
anywhere else — in the head, in memory across operations — would be a
second representation of the chain. So the layer renders, splices, and
re-stores. Measured cost: the backing store grew to 268.9 MB for an
11.0 MB logical tree (24×), almost all of it superseded chains left
unreachable by append+swap (reclamation is banned this phase).

**Verdict: honest model edge, the phase's central cost finding.** The
same literal-reference opacity that made phase-2 queries run over the
render makes version-to-version sharing unreachable for the live layer.
(The offline pass, which IS chartered to walk chains, has no such
limit — one plausible future shape is condensation doubling as history
compaction.)

## 16. Fixed chunk boundaries visibly hurt dedup — charter caveat confirmed

80 occurrences of admitted blocks were unreplaceable because they span
the fixed 64 KiB chunk boundaries (the 5 MiB text file's repeated block
lands across every boundary). The charter pre-ruled fixed boundaries
for v1 and asked for exactly this note.

## 17. Faked syscalls (charter §6 requires the list)

- `chown`: accepted and ignored.
- hardlinks (`link`): EPERM — a hardlink is two references to one head
  with shared identity, which the reference-tree cannot express.
- `atime`/`ctime`: reported as mtime; only mtime is stored.
- `fsync`/`flush`: no-ops — every write is already at rest when its
  firing returns; there is nothing pending to flush, ever.
- directory metadata (mode/mtime of directories): taken from the
  backing directories, not modeled.
- non-UTF-8 filenames: refused (references decode as UTF-8).

## 18. Reads render the whole chain, per syscall

The kernel reads big files in ≤128 KiB bites; each bite demands the
head and fires the entire chain, then slices. Measured: 32.3 firings
per read call over the acceptance workload (an 81-file chain fired ~40
times to read one 5 MiB file once). No caching is pre-ruled for v1 —
the number IS the measurement, and the spec's identity-cache (unbuilt)
is exactly what it argues for.

## 19. Metadata needed a record convention — phase-2 finding #8 recurs

The head carries five "\n"-terminated literal fields (type, chain ref,
size, mtime, mode). The layer owns the convention it renders and
splits, as the phase-2 clients did. Same verdict: convention lives in
the world; the library and grammar stay convention-free.

## 20. Idempotency forced the pass to preserve chunk topology

First attempt regrouped pieces into fresh 64 KiB chunks on rewrite;
that MOVED the fixed boundaries, so blocks that were span-rejected on
run 1 became replaceable on run 2 — run 2 rewrote chains, violating the
charter's idempotency rule. The fix: rewrites keep every container's
boundary where it was, re-emitting only touched chunk files and reusing
untouched references in the new chain. Boundary stability, not
content stability, is what makes re-running a no-op.

## 21. What produced zero friction in phase 3

- **git ran unmodified** — init, add, three commits, log, checkout,
  fsck, index renames, lock files, reflog appends — on a filesystem
  whose every file is a firing pattern. No syscall behavior had to be
  bent for it (only faked metadata, #17).
- **Crash consistency cost zero code.** Emits inside a write fire
  left-to-right with the head last, inside one indivisible firing;
  SIGKILL + remount needed no recovery, no journal, no fsck of ours —
  acceptance 3 passed with literally no code path for it.
- **No locks under a real kernel's concurrency.** One loop, firings
  never yield; the kernel's interleaved syscalls serialize at the
  mount, exactly the charter's §5 prediction.
- **Condensation verification is trivial** because rendering is
  deterministic: checksum before, rewrite, render, compare — no "did
  the optimizer change semantics" class of doubt.

---

# Phase 4 — computation pressure + shape condensation (2026-07-09)

## 22. Constant folding is corpus-relative

The three board posts landed in the same minute, so the promoted message
shape folded the timestamp string in as a CONSTANT alongside the real
punctuation. Render-verified correct for every rewritten instance, and
future posts are unaffected (they spell the shape out until a pass sees
them) — but a small corpus over-folds. The ≥3-instance rule guards
recurrence, not coincidence.

**Verdict: engineering wrinkle with a real lesson** — shape admission
quality scales with corpus size, like every induced grammar.

## 23. In-place rewrite was forced by literal references

Phase 3's pass could give rewritten chains fresh references because only
heads pointed at them. Board messages are different: their references are
baked into OTHER messages' demand nodes, so fresh refs would cascade a
rewrite through every downstream demander. The pass instead replaces file
content in place, render-identical, at the same reference.

**Verdict: honest model edge** — in a literal-reference graph, "supersede
by new ref" only works at the head layer; interior nodes can only be
replaced behind their name.

## 24. What produced zero friction in phase 4

- **Eight computations composed; five were added** (see LIBRARY.md).
  max/min fell out of sort+last, average out of div∘(sum,tally), the
  budget join out of sub across two demands. First sub-linear phase.
- **Refusals compose**: average-of-empty-ledger refuses with "division
  by zero" propagated from three compositions deep; numeric sort over
  text lines refuses with "not a number". No error-handling code exists
  anywhere in the workload.
- **Shape promotion worked on the first corpus it met**: recurring
  composition shapes became resident structures, instances shrank to
  shape-ref + operands, everything rendered byte-identical through a
  router reload — the arrival-is-recognition property now exists.

---

# Phase 5 — the wire (2026-07-09)

## 25. Discovery is namespace enumeration, and the temptation was a manifest

The sync driver finds what to ship by walking the source world's
directories (the readdir precedent) and selecting on backing mtime. The
convenient alternative — a manifest of what exists / what changed — is
the banned index wearing sync clothes. Refused. The driver's only state
is its own high-water mark, held on its side of the edge like rsync's.

**Verdict: discipline held; the reference tree was already the catalog.**

## 26. Dictionary delivery is restart-priced

B could STORE condensed instructions it had no residence for (moving
opaque values is not interpreting them) but firing refused with
"unknown structure id 101" — and after lib/ was shipped, B's router had
to be reloaded before the shapes were resident, because residency
changes only at router start (A1's conservative reading, all phases).
Load-on-first-reference would be the natural A4 reading — nothing is
resident unless demanded — but it changes structure residency at
runtime, which touches A1. Open question for Jocke: DECISIONS.md §2.2.

**Verdict: honest model edge, cheap in practice** (a router restart is
milliseconds; state is files), **but the lazy reading is attractive and
needs a ruling, not an implementation.**

## 27. What produced zero friction in phase 5

- **No wire protocol was designed.** The stored form is the wire form;
  replication is emits carrying opaque files as values; the client
  framing from phase 1 carried node-to-node traffic unchanged.
- **No format negotiation, no import step.** B fired A's instruction
  bytes natively the moment residence matched — 26 query results
  byte-identical across nodes.
- **The refusal named the cure.** "unknown structure id 101" is a
  self-describing bootstrap protocol that nobody wrote: the error
  grammar node plus condensed traffic equals dictionary distribution.
- **Old and new interoperate.** An uncondensed post synced after the
  condensed corpus fired fine with no reload — spelled-out shapes and
  promoted shapes coexist in one chain.
- **Honest number, recorded**: at this toy scale, minimal JSON of the
  same logical data (346 B) is SMALLER than the full sync's wire bytes
  (1,025 B — per-file emit wrappers and references dominate tiny
  files). The model's wire story pays at the delta (163 B for one new
  post, two files) and in what never had to exist: schema, parser,
  version handshake. Scale is where shared residence should win;
  unmeasured until a bigger corpus.

---

# Phase 6 — compaction and the render cache (2026-07-09)

## 28. The cache is a store, and the invisibility test is checkable

The render cache is the first component in the project whose existence
changes nothing but time — and that claim is not rhetoric, it is an
assertion: the benchmark reads the whole tree raw and cached and
compares checksums. It held. The discipline that made it checkable is
determinism plus write-once references: a cached entry can never be
wrong, only absent.

**Verdict: the spec's cacheability story, confirmed in the world tier.**
Note honestly: this is a demander-side memory, not the model's licensed
below-demand identity cache — chains contain demands, so the soundness
comes from the mount being the store's only writer (fresh reference per
write), not from the spec's determinism clause alone.

## 29. Heads are the floor

Cached reads still cost 2.84 firings per read call — the head demand
per operation. Heads are the one mutable indirection in the design, so
they can never be cached, so every operation pays one firing to cross
the mutable frontier. That is the durable price of identity-over-time
in this model (the phase-1 finding, now as a floor constant).

**Verdict: honest model edge, quantified.**

## 30. What produced zero friction in phase 6

- **GC needed no machinery.** Roots are the heads directory,
  reachability is the demand graph already stored in the chains,
  deletion is os.remove. 4,390 files and 263 MB of superseded history
  vanished with zero refcounts, zero epochs, zero pauses that matter.
- **Cache invalidation genuinely had nothing to do.** A write stores a
  fresh chain reference, which is a natural cache miss; the overwrite
  test passed against both the warm cache and a cold raw remount. The
  spec's claim that invalidation is deleted was true here for the
  boring reason: nothing a cache key names can ever change.
- **The two passes compose.** Condense then compact leaves a store at
  roughly half the plain-ext4 tree with zero unreachable bytes.

---

# Phase 7 — multi-writer: merge is a query (2026-07-09)

## 31. The lost-update window reappeared at the replication layer

Naive bidirectional sync failed the harness on first run: node A shipped
its STALE copy of bob's head back over node B's fresh one — §2.1's
window, reopened by copying instead of posting. The cure was not
coordination but the same principle that closed it between writers:
ownership. A node ships only the references its writer owns
(`sync(..., prefixes=...)`); heads then have one writer AND one shipper.

**Verdict: honest model edge, and a satisfying one** — the fix is the
phase's own thesis applied to itself. Mutable heads are safe exactly as
far as single-ownership extends, and no further.

## 32. Chronology is a convention in the rendered line

The merge sorts lines textually; time ordering works because the posts
render a sortable timestamp prefix. Same class as phase-2 #8/#9: the
convention is the workload's own, rides as values, and is spoofable by
content that fakes a prefix. A writer that lies about time reorders the
merge — exactly like every timestamp-ordered system ever built.

**Verdict: model edge consequence, known shape.**

## 33. What produced zero friction in phase 7

- **Convergence was free.** Merge = sort∘concat over demanded chains —
  deterministic, so both nodes firing the same instruction over the
  same replicated data are byte-identical by construction. Nobody wrote
  a conflict resolver; there is nothing to resolve because nothing was
  ever contended.
- **Views cost nothing and live nowhere.** Newest-2 and alice-only are
  compositions over the merge instruction; different readers can hold
  different merges over the same history without touching storage.
- **Divergence is honest, not an error.** Unsynced nodes differ because
  the world differs across a demand boundary — the spec's own words —
  and re-syncing reconverges without any repair step.
- **Zero new structures, zero grammar changes** for the entire phase.

---

# Phase 8 — open-key grouping (2026-07-09)

## 34. The index turned out to be content

Phase 2's #10 left open-key grouping as standing falsification
pressure: keys inside rendered content are unreachable without a
resident parser. The resolution required no parser and no index
component: the post firing also appends the author to a projection
chain — one more unsent-instruction chain, swapped atomically in the
same indivisible firing as the message. The key set is then a query
(`uniq∘sort∘demand(authors)`), and grouping proceeds with keys the
demander just learned. The projection is ordinary content: demandable,
replicable by sync, condensable by the passes, compactable, owned by
its writer.

**Verdict: FRICTION #8's prediction confirmed** — field-precise queries
were answered by a different *stored* shape, not by read-side
machinery. The cost is honest and known from every database ever built:
the writer pays for the projections readers will want, and a projection
not written at post time cannot be conjured later without re-posting
history (a world-side migration, like any backfill).

## 35. What produced zero friction in phase 8

- One structure (`uniq`, a pure adjacent-dedup fold) covered key-set
  extraction; the rest was composition over phase-2/4 structures.
- Four emits — message, projection entry, two head swaps — in ONE
  firing kept post atomicity with no new mechanism.
- A never-before-seen user was discovered by the same query that found
  the old ones; no code anywhere holds a user list anymore.

---

# Phase 9 — scale on real content (2026-07-09)

## 36. Universality-compression is recurrence-bound, and real source has little fat recurrence

On 11 MB of real stdlib source, condensation admitted 13 templates
worth 158.8 kB — the store landed at −1.0% vs plain ext4, not the −48%
of the header-heavy phase-3 corpus. And the tar.gz anecdote is 2.56 MB
against our 10.99 MB wire: gzip wins 4× on unique content, because the
model's compression is cross-file reference-sharing, not entropy
coding, and single-version source code simply doesn't repeat itself in
≥512-byte blocks. The spec's §7 "degrades gracefully" clause is exactly
what happened — literals rode as literals, fidelity held, storage sat
at ext4 par — but §0's "everything stays small" needs its honest
qualifier: the model's wins are dedup-shaped (versions, copies, shared
boilerplate, templates), never entropy-shaped. Corpora with history
recur; a snapshot mostly doesn't. (Transport-level compression of the
wire would be a world-side channel property, like TLS; noted, not
built.)

**Verdict: the phase's central finding, and a real spec-rhetoric
correction.**

## 37. Edit deltas re-ship whole files

Three small appends produced a 153 kB delta — the #15 write
amplification surfacing at the wire: an edit re-stores (and re-ships)
every chunk of the file. rsync would have moved a few kB. Chunk-level
reuse across versions stays blocked by literal-reference opacity (#15),
and the wire inherits the cost.

**Verdict: known edge, now priced at scale.**

## 38. What produced zero friction in phase 9

- **637 real files, 11 MB, byte-identical** through ingest → condense →
  compact → cold remount read-back. Nobody wrote this content for us.
- **The universal tier did not move: 11 → 11.** Twenty-five times the
  volume of everything previous, zero new capability needed — the §6
  stake at scale, held.
- **Throughput is usable for a pure-Python falsification prototype**:
  6.7 MB/s ingest, 7.6 MB/s read-back through FUSE, 4.7 s to condense,
  sub-second replication of the full store.
- **Every pass composed**: condense → compact → sync ran back-to-back
  on a store none of them was written against.

---

# Phase 10 — the recurrence-shaped corpus (2026-07-09)

## 39. The gzip rematch, on dedup's terrain: won

Eight snapshot generations of an evolving source tree, 30.4 MB logical,
5.3 MB of unique content. gzip entropy-codes but cannot see a duplicate
past its 32 KiB window, so tar.gz holds 7.63 MB. Condensation dedups by
reference across the entire store: 1,506 templates, and the
condensed+compacted store rests at **4.60 MB — 1.7× smaller than
tar.gz, and below the perfect whole-file-dedup floor (5.34 MB)**,
because recurring blocks inside *modified* files dedup too. Full
replication to a second node moves 4.71 MB of wire. Fidelity verified
by cold-remount tree checksum.

Paired with phase 9 (#36), the compression story is now complete and
honest in both directions: unique content → gzip wins 4×; recurring
content (versions, backups, copies) → the model wins 1.7× over gzip
and beats whole-file dedup. Universality-compression is dedup-shaped,
and dedup-shaped corpora are what most stored bytes in the world
actually look like.

**Verdict: the model's storage claim, finally standing on the right
terrain — and the win needed nothing new: the phase ran entirely on
machinery from phases 3 and 6.**

## 40. What produced zero friction in phase 10

- Zero universal additions again (11 → 11); zero code written for the
  phase beyond the harness itself.
- 1,506 template admissions and thousands of rewrites went through the
  same fired-emit path as everything else, render-verified, in 13.6 s.
- The condensed store and the replication wire are within 2% of each
  other — stored form = wire form held at scale, after condensation.

---

# Phase 11 — the native fire loop (2026-07-09)

## 41. Cold reads are IOPS-bound: reference-chasing costs opens

Warm, native firing delivers 412 MB/s vs 479 MB/s for raw reads of the
plain tree — interpretation costs 14%. Cold, firing drops to 0.42× of
raw reading: rendering 1,228 files opens ~5,000 small store files
(heads, chains, chunks, templates) against the corpus's 1,228, and
cold-cache open latency dominates. The model's store trades bandwidth
(6.6× less data read) for operations (4× more opens). On
bandwidth-limited media (network filesystems, throttled cloud disks)
that trade wins; on latency-limited media it loses. A packed layout
(many chains per container file, references as offsets) is the obvious
engineering answer and a real structural question — container files vs
one-instruction-one-file — for a later ruling if it matters.

**Verdict: honest cost, newly visible only at native speed.**

## 42. The Python-speed folklore corrected

Direct Python rendering of the store runs 85 MB/s — the 5-8 MB/s
numbers of phases 9-10 were dominated by FUSE round-trips, not by the
interpreter. Native is 5× direct Python and ~50× the through-FUSE path.
Recorded so the report never implies Python was 1000× off.

## 43. What produced zero friction in phase 11

- **Byte-compatibility held on first contact**: a 300-line C program
  fired stores written by the Python runtime, and the checksum of every
  rendered byte matched the plain corpus (`fold=8549ffed37065481` from
  both paths). One representation, two independent interpreters, zero
  format code.
- **The section-0 kill condition did not trigger**: warm firing is
  within 14% of `cat` while reading 6.6× fewer bytes from disk. The
  interpretation the model adds is nearly free; the movement it deletes
  is real.
- **Templates-as-residence worked exactly as drawn**: 1,506 blocks
  loaded once at start, then every reference a memcpy from warm memory.

---

# Phase 12 — the tool (2026-07-09)

## 44. Dogfood findings from am.tool

- **The ≥3-file admission rule makes dedup warm up late**: snapshot 1
  admits nothing, snapshot 2 admits only what already recurred within a
  generation, and full cross-version dedup arrives with snapshot 3
  (+874 templates at g3). A backup tool would want blocks shared by
  just two snapshots to dedup too; the threshold was charter law for
  the phase-3 experiment and is kept as-is pending a ruling. Cost: the
  first two snapshots store closer to 2× than 1×.
- **Deltas are chunk-grained, not edit-grained**: pushing one new
  generation (6 edited files, 1 added) moved 0.16 MB — 7% of a full
  snapshot, vs rsync's few kB. The remaining gap is #15/#37 wearing its
  last costume: an edited file's changed chunk re-ships whole.
- **The workflow answer to #37 held**: snap → condense → compact →
  push means the wire carries condensed chains and references into
  templates the replica already holds. No rule changes were needed.

## 45. What produced zero friction in phase 12

- The tool is ~250 lines of world-side CLI and contains no model
  machinery at all — every capability (immutable snapshots, restore of
  any version, verification, replication, delta transport, browsing
  history as a filesystem) was already lying in the chartered parts,
  waiting to be composed.
- Snapshot immutability required no code: a snapshot is a namespace
  nothing ever writes into again, because nothing is ever overwritten.
- The replica needed no import, no schema, no format version: it is a
  store like any other, and a CLI process loads residency at start, so
  even the §2.2 restart question never surfaces in tool-shaped use.

---

# Phase 13 — the end-to-end metric (2026-07-09)

## 46. The pipeline comparison, honestly annotated

Challenged by Jocke ("did you just compare python vs c?") and tightened
in response: wall time WAS Python-vs-C (now labeled not-comparable);
crossings are byte counts and language-independent; and the design
asymmetry (their log+scan vs our projection) was measured away by
adding a third pipeline — conventional WITH the same projection. The
honest ladder: 14.15 (naive) → 2.68 (indexed) → 1.79 (model) crossings
per payload byte. The 1.5× residual vs the best conventional design is
the pure one-representation dividend: encode-at-birth + decode-at-ingest
are two full-payload crossings the model structurally cannot pay.
Original annotations:

- **Wall time loses in Python and it is printed next to the win**:
  ingest 6.4 s vs 0.4 s, queries 1.7 s vs 0.3 s. A pure-Python
  interpreter races C-accelerated json and loses; phase 11 already
  measured what happens when the fire loop is native (0.86× of cat).
  Crossings are the concept; wall time is the implementation.
- **The model's crossings floor is ~1 + renders**: 1.0× for
  construction (information becomes an instruction once) plus ~0.4× per
  query pair for the rendered projection each firing materializes —
  charged with no in-flight discount. The write-side projection is what
  keeps a query's marginal cost at the projection's size instead of the
  full log's; without it the two sides converge.
- **Design fairness, stated**: the conventional side is the canonical
  log+scan service. An indexed design shifts query cost into ingest-time
  machinery — the same class the model pays for openly as its
  projection, in both counters.
- **Round trips show the literal-reference tax**: the model's copy
  bytes include per-record instruction framing and chain-entry files;
  3.27× vs the payload is not free, just 4.8× cheaper than the
  conventional pipeline's shuttling.

---

# Phase 14 — the real build (2026-07-09)

## 47. Native closes the interpreter gap and exposes the layout gap

amd (a ~550-line C router: full grammar, all 11 structures, the emit
terminal, templates, the phase-1 wire protocol) passes the strong
gates: identical ingest through Python and through amd leaves
BYTE-IDENTICAL world trees, answers match across four pipelines, and
refusals behave. The true clocks then say, on the record-granular job:

- queries: 1.695 s (Python) → 0.113 s (amd) — the interpreter gap was
  15× and it is gone; but the best conventional design answers in
  0.005 s, because its projection is ONE file and ours is a chain of
  2,000 — each query is 2,000 open()s.
- ingest: 0.3 s conventional vs 3.0 s amd, both disk-bound — the model
  writes two FILES per record (20k creates); the conventional log
  appends to one.

So the residual cost is not interpretation and not architecture-of-
representation (phase 13 settled crossings) — it is the
one-instruction-one-file LAYOUT, which taxes every fine-grained
workload with an open()/create() per reference (the same IOPS wall as
phase 11's cold reads and #41). File-granular workloads (phases 9–12)
never felt it; record-granular ones are 7× end-to-end behind the best
conventional design because of it. Packed containers (many unsent
instructions per file, references as names-with-offsets) are the
obvious engineering answer and a genuine structural question — whether
a reference may name into a container — escalated to DECISIONS §2.4,
options written, NOT implemented.

One symmetric note: construction (Python encoder, 0.117 s) is 3× the
C-json encode; in a native producer it would be noise. The stack the
concept implies is now one small C file; everything else is worlds.

---

# Phase 14 addendum — the rented store (2026-07-09)

## 48. "It only works because you do the operations per file" — correct

Jocke's critique, admitted into the record: the model's storage story
("no database, no index, no store component") works by DELEGATING
allocation, naming, lookup and durability to the filesystem — which is
itself a database. The deletion was real only in the sense that no
SECOND storage system was built. The subsidy holds at file granularity
(phases 9–12, the wins) and collapses at record granularity, where
ext4 charges an inode + dentry + 4 KiB block for every 30-byte record
(phase 14's 7×, phase 11's cold reads). The §2.4 packing proposal is
accordingly reframed as what it is: re-importing a small store
component (an allocator, content-blind) below the granularity where
the OS's can be rented — while the representation-level deletions
(formats, parsers, serializers) genuinely never return.

**Verdict: the sharpest external correction of the project**, and it
came from outside the friction log's own habits.

---

# Phase 15 — the compute half (2026-07-09)

## 49. The model branches on data, the world branches on effects

Conditional logic turned out to be composable from the existing library
with nothing added: the condition is computed as a value
(`tally∘pick` → "1"/"0") and SELECTS between alternatives that exist as
data (`select` over "1 approve\n0 decline\n"). 208 sequentially
dependent decisions — each depending on the balance left by all
previous ones — agreed with a plain-Python reference implementation on
every single one. But the boundary is now exactly drawn:

- the model can DECIDE (branch on data, eagerly — both alternatives are
  bytes; the untaken one costs its rendering, like SQL CASE or SIMD);
- the model cannot choose which EFFECT fires: the world receives the
  decided value and performs the corresponding emits (the pump);
- the model cannot loop: repetition is either chain-shaped (data) or
  the world pumping one firing per stroke;
- derived sequential state must be MATERIALIZED by the pump — a
  computed decision becomes the next stored literal only through the
  world, the second-class-references wound in compute clothing.

**Verdict: the name "activation model" is now honestly scoped.** It is
a decision-and-rendering engine with world-side control flow — a
programmable calculator with perfect memory, not a computer. Whether
that boundary is a flaw or the design depends on what Jocke wants the
model to BE; nothing in the spec promises loops, and A4 arguably
forbids them (nothing fires uncommanded — including the next iteration).

## 50. What produced zero friction in phase 15

- Branching cost ZERO structures and zero grammar. The falsification
  bet ("computation shapes balloon the library") failed to trigger on
  the hardest shape yet.
- The processor is stateless by construction: killed mid-run, rebuilt
  by demanding three heads, zero drift across the restart.
- The audit trail was free: the events chain IS the log, and
  "how many declines" is one tally over it.

---

# Phase 16 — the memory path (2026-07-09)

## 51. The residency mechanism is real in the traffic domain; the time
## domain belongs to the prefetcher (on this machine)

Chartered by the critique Jocke relayed: nothing had ever measured the
memory hierarchy — the actual §0 mechanism. Now measured (compiled C,
same kernel, same logical stream, answers asserted identical; cachegrind
with a pinned 32K/8M hierarchy; recurrence ratio p swept):

- **Traffic: the claim holds, cleanly.** At p=99, the instruction-form
  stream is 0.29× the raw bytes and last-level cache misses fall to
  0.15× (6.7× fewer) — references into an L1-resident template table
  really do convert recurrence into cache hits. The pre-stated
  falsification case behaved exactly as predicted: at p=0 the grammar
  is pure overhead (+13% bytes, +13% misses).
- **Time: no conversion on this hardware.** Single-threaded, the walk
  costs 1.1–1.5× wall despite the miss reduction, because a linear scan
  is the hardware prefetcher's best case — DRAM latency never surfaces,
  so saved traffic buys no saved time, while varint/tag decoding costs
  real instructions. Four-core contention on this virtualized box did
  not saturate bandwidth enough to flip it (~parity at p=99).

The sharp version of the finding: **the conventional world has hardware
that hides the cost of its own waste for sequential streams.** The
model's traffic win is real and deterministic; it becomes a TIME win
only where bandwidth (or energy) is the scarce resource — many cores
saturating DRAM, NUMA/CXL distance, latency-exposed access patterns,
or joules-per-bit (bytes moved is the energy proxy; unmeasurable in
this container). Those conditions exist in real datacenters and are
exactly §0's "moving a byte costs orders of magnitude more than
computing on it" — but they could not be produced cleanly in this VM,
and that limit is recorded rather than papered over.

**Verdict: §0's mechanism confirmed at the traffic level; its
time-domain payoff is condition-dependent and remains the open
empirical question for real hardware with PMU access.**

## 52. Store-assigned names couple write latency to the round trip

Phase 17. With file-path references the WRITER names the next link
before the store ever sees it, so ingest pipelines blind: phase 14
sent 10,000 record instructions in one stream and read 10,000 acks
after. With pack offsets the store assigns the name at append time and
the writer cannot construct link n+1 until it holds the name emit
RETURNED for link n. Ingest became round-trip-per-record by data
dependency, not by implementation. The trade then lands strangely
well: amx STILL ingests slightly faster than amd (2.5–2.6 s vs
2.7–3.4 s over repeated runs) because one pack append costs so much
less than two file creates that it eats the whole round-trip penalty
— but against the conventional stream (0.2 s) the ~10× gap is now
mostly latency floor (10,005 round trips), where amd's gap was IOPS.
That is the model fighting back against its own ruling: §2.4's cheap
demands (pointer arithmetic, no syscall — queries 7–9× faster than
amd) moved naming ownership from the writer to the store, and the
write side pays in coupling, not in bytes. Phase 7's discipline
(one writer per head) caps the damage — independent chains could
overlap their round trips — and a writer could ask for the tail cursor
and name ahead speculatively, but that is a second representation of
the store's allocation state living in the client, so it is refused
here. Recorded as a trade, priced both ways.

## 53. What the pack did NOT change, and one engineering note

Phase 17 added ZERO structures (universal tier still 11), zero grammar
nodes, zero wire changes; the same query instructions phase 13 built
byte-compatibly fire against pack, files, Python, amd, and amx. The
residual query gap to the best conventional design (0.010 s vs
0.004 s, was 0.113 s) is no longer layout: it is rendering — every
query fires the full 2,000-link chain because amx has no render cache;
phase 6's demander-side cache is the chartered answer if it ever
matters. Engineering note: -O2 inlined dispatch and demand-resolution
into the recursive fire function, making each chain link cost ~9 KB of
stack (segfault past ~1,200 links). Keeping them out of the recursive
frame (noinline) put the frame at 256 bytes, so the MAX_DEPTH refusal
fires long before the stack can — a refusal, never a crash.

## 54. The fire loop never used recognition — caught by Jocke

Phase 18, chartered by "wait, you never use cached shapes?" — correct,
and the miss was structural: recurrence was exploited for BYTES
everywhere (condensation, shape promotion, resident templates — the
storage, wire and cache-traffic wins) while every engine decoded each
ARRIVING instruction generically, byte by byte, ten million identical
decodes for ten million arrivals of one shape. "Arrival = recognition"
had been implemented for representation and never for execution. The
answer built and measured (`membench` mode `amc`): first arrival of a
shape compiles a plan (byte skeleton with values masked, fixed value
offsets), later arrivals match by masked word-compare and load at
offsets like the raw walker. Gated byte-identical at every recurrence
ratio. RESULT, honestly: at this workload's 3-field/15-byte records it
LOSES to generic decode (0.19 s vs 0.17 s at p=99) — a tiny record with
predictable branches decodes in ~10 cycles and the plan dispatch costs
more than it saves. Kept in the tree as the tested-and-rejected path;
the scaling hypothesis (wide shapes: decode grows, recognition stays
two compares) is stated, untested. The hunt for where the overhead
ACTUALLY lives produced #55, which is worth more.

## 55. Reference width entropy: the coin-flip branch, and the first
## time-domain wins

Found decomposing #54's numbers. The bench template sids (100–163)
straddle the LEB128 one/two-byte boundary, so the WIDTH of every hot
reference is a per-record coin flip — an unpredictable branch that
flushes the pipeline mid-walk. Allocating hot sids in one width band
(base 128: all two-byte — one trailing arg, zero grammar change) made
the walk-dominant kernel **1.9× faster** at p=99. With that fixed, on
the same VM that had refused a time win for two days:

- walk-bound job, ONE core:   am 0.46× of raw (2.2× faster)
- walk-bound job, all cores:  am 0.44× of raw (stable, ABBA, 3 repeats)
- compute-heavy job (fnv1a):  am 1.12× — representation barely matters
  when the task kernel dominates, exactly as §0 would predict.

Two findings in one: (1) §0's traffic win DOES convert to time — in
the regime where data movement is the work, and even single-core; the
earlier "no conversion" verdicts were measuring a compute-bound kernel
through a branch-entropy handicap. (2) Reference ALLOCATION is a real
world-side performance discipline: hot resident structures deserve a
uniform-width sid band (DECISIONS 1.19). Phase 16's pinned baselines
stand unchanged (default base 100 = the honest worst case).
