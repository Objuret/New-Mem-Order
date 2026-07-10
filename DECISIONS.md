# Decisions

Two kinds of entries, kept separate on purpose:

1. **Judgment calls made under delegated authority.** The brief delegates
   the workload's shape ("a 'thread' is whatever the model makes it —
   discovering that shape IS the experiment") and engineering details the
   spec already covers. These were decided and built; they are recorded
   here for Jocke's review and are reversible.
2. **Open structural questions.** Where the spec is genuinely silent and
   the decision is structural, nothing was implemented. Options and a
   recommendation are recorded; they have no force until Jocke decides.

---

## 1. Judgment calls made (built, reviewable)

### 1.1 Thread shape: chain of unsent instructions + head reference file
A message at `msgs/<id>` is `concat(demand(<prev>), ...fields)`. A thread
head at `threads/<name>` is a literal node holding the newest message's
reference. Reading = demanding; posting = one firing with two emits.
*Basis:* brief step 6 delegates the shape; spec §2 (Terminal structure)
explicitly covers emit-to-disk touching shared world-state, and brief
step 5's "the demander holds the reference" is satisfied — the fixed head
path is the reference clients hold.

### 1.2 Head replacement is world-state change, not model mutation
Overwriting `threads/<name>` happens past the model's edge, through the
one terminal, on the one router, inside one indivisible firing. A2
applies up to the terminal, not past it (spec §2).

### 1.3 Byte encoding: single-byte tags + unsigned LEB128 varints
Spec §8 fixes "compact binary — structure IDs + values + wiring, nested";
the concrete varint/tag choice is engineering. Self-delimiting, walkable
without any decode-to-tree step.

### 1.4 Return path: router wraps output as a literal/error node
"The demand is the return path" (spec §2, Output). No socket-send library
structure was needed for it; replying to the demander is router
mechanics, like a function return.

### 1.5 Instrumentation lives outside the model
`stats.log` (router) and `report.py` (directory walk, overhead counts)
exist only to produce the brief's measurements. Nothing in the model
reads them; deleting them changes no behavior.

### 1.6 (Phase 2) Queries compute over the rendered chain output
The stored chain fires to one thing — the rendered thread — so the three
queries are filter/fold/take structures over that in-flight value, with
the record convention (line terminator, "] user: " marker) entering each
query instruction as literal operands from the demander. The library
holds no convention. *Basis:* the phase-2 rules fix conditions-as-values;
the alternative (field-precise queries) would change the stored shape,
which phase 2 froze ("over the existing board data"). Consequences
logged as FRICTION.md #8–#9.

### 1.7 (Phase 2) "Per user" keys come from the demander
`count` fires one `tally` per user named by the client. Open-key
grouping was refused — it needs key-extraction machinery, i.e. a
resident parser (FRICTION.md #10, LIBRARY.md not-added list).

### 1.8 (Phase 2) Structure-definition details pinned in the library
Segment semantics (delimiter is a terminator; FRICTION.md #12) and the
number convention (decimal ASCII for `tally` output and `last` input;
FRICTION.md #11) are definition details of the new structures, decided
as engineering the way varints were in 1.3.

### 1.9 (Phase 3) The head's five-field record
A file's head renders five "\n"-terminated literal fields (type, chain
ref, size, mtime_ns, mode). *Basis:* charter §4/§6 pre-rule what the
head holds; the record convention is the layer's own, entering and
leaving as values (the phase-2 pattern, ruling 1.6). Numbers ride as
decimal ASCII per ruling 1.8.

### 1.10 (Phase 3) Promoted structures persist as unsent instructions
A condensation admission is a zero-operand content template whose
definition lives at `store/lib/<sid>` as a literal instruction, fired
once at mount and resident thereafter. *Basis:* charter §7 pre-rules
admission; A1 requires runtime immutability, satisfied because growth
happens only in the offline pass; storing the definition as an
instruction keeps "never store raw bytes outside literal nodes" (§4)
and adds no second representation. Listing `store/lib/` at mount is the
same act as readdir over a directory of references (§4's sanctioned
mechanism), not an index.

### 1.11 (Phase 3) Rewrites preserve chunk topology
The pass re-emits only touched containers and reuses untouched chunk
references. *Basis:* charter §7 requires idempotent re-runs; moving the
fixed boundaries during rewrite breaks that (FRICTION.md #20).
Engineering detail of the pass, same class as 1.3.

### 1.12 (Phase 5) The world may MOVE unsent instructions opaquely
The sync driver copies stored instruction files between worlds as
values inside emits, never interpreting the bytes. *Basis:* spec §4
already grants "deleting an unsent instruction = deleting a file, same
as now"; moving is the same class of world act, and §8 makes the stored
form the wire form by definition. The one-interpreter rule is intact:
only firing interprets.

### 1.13 (Phase 5) Replication discovery = namespace enumeration
What to ship is found by walking the source world's directories plus
backing mtime — the readdir precedent (phase-3 §4). A change manifest
was refused as the banned index (FRICTION.md #25). The driver's
high-water mark is driver-side state, like rsync's.

### 1.14 (Phase 6) Compaction = deletion by reachability
`am/compact.py` removes chain files no head reaches. *Basis:* spec §4
grants deletion of unsent instructions as a plain world act; the heads
directory is already the root set; the reachability walk is the
chartered offline structural walk (same class as condensation). No GC
component exists — no refcounts, no roots registry, no pauses.
Render-verified before/after inside the pass.

### 1.15 (Phase 6) The layer's render cache is demander-side memory
The mount memoizes chain renders by reference. *Basis:* a demander may
remember outputs it received (phase-1 clients kept refs; nothing in the
spec obliges re-demanding); serving that memory is sound HERE because
the mount is the store's only writer and every write goes to a fresh
chain reference, and the condensation pass is render-identity-verified
across mounts. Heads are mutable and are never cached. This is NOT the
spec's below-demand identity cache (chains contain demands); it leans
on the write-once discipline, and it is stated so in FRICTION.md #28.
`--raw` disables it; phase3_tests.py pins `--raw` so the v1 raw-model
numbers remain the published baseline. Checkably invisible: the phase-6
benchmark asserts raw and cached full-tree checksums are identical.

### 1.16 (Phase 7) Write ownership partitions heads AND replication
Each writer owns its head (one writer per mutable reference — the
terminal-binding idea applied at the data layer), and a node ships only
its writer's references. *Basis:* spec §2 Terminal structure for the
ownership principle; workload-shape delegation for the rest; forced by
FRICTION.md #31 when naive bidirectional sync reopened the lost-update
window at the copy layer.

### 1.17 (Phase 12) The tool is a world-side composition
`am.tool` (snap/restore/verify/stats/serve/push/mount) is a CLI that
composes existing chartered machinery: layer puts for ingest, the
condensation and compaction passes after every snapshot, phase-5 sync
for replication, the FUSE binding for browsing. Snapshots are fresh
namespaces `fs/<label>/…` (immutability by never-overwrite); the push
high-water mark lives in a sibling file OUTSIDE the store (driver-side
state, ruling 1.13). No new structures, no grammar changes, no rule
changes; the ≥3-file condensation threshold is kept as charter law
even though backup use would prefer 2 (FRICTION.md #44) — that change
awaits a ruling.

---

## 2. Open structural questions for Jocke (NOT implemented)

### 2.1 Should posting be closable into one firing?

**RULED by Jocke, 2026-07-08: stays open by design.** The lost-update
window is an accepted trade of literal references. Do not fix, do not
reopen. Options below kept for the record only.

Today a post is two firings (demand head → fire message+head emits), so
two concurrent posters can orphan a message (FRICTION.md #2). The plain
spec offers no way to do better, because the new message's chain link
must be a *literal* demand reference, and the current head reference is
only knowable by demanding it.

- **Option A — leave it (status quo).** The race window is inherent and
  mild: nothing tears, a message merely becomes unreachable from the
  head. Multi-writer coordination stays a world problem, like two
  programs writing one file today.
- **Option B — a constructor structure** (e.g. `make-demand-node`:
  value → demand-node bytes). A post could then be ONE firing: demand
  head, build the chained message around the result, emit both. Closes
  the race via fires-whole. Cost: a structure that turns computed values
  into demand references, which the stored file makes literal again —
  arguably laundering exactly what spec §2 forbids ("never a computed
  one"). Needs Jocke's reading of A4's intent, and a spec amendment if
  accepted.
- **Option C — an append-emit terminal** and a multi-node stored-file
  grammar, making a thread one growing file. Deletes the head file and
  the race, but changes the grammar (a file = a series of nodes fired in
  sequence) — a spec §2 amendment, and it makes the stored form diverge
  from "one instruction, one file."

**Recommendation: A for the prototype phase** (it is what's built — i.e.
nothing was added); revisit B only if a workload needs contended
multi-writer posting to be loss-free. B is the smaller amendment if one
is ever wanted.

### 2.2 May a router make a structure resident at first reference?

Phase 5 delivered promoted structures across the wire: the receiver
stored them fine but could not fire condensed chains until its router
restarted, because residency changes only at router start (the
conservative A1 reading used in every phase). The refusal-then-ship
bootstrap works and is what's built; the question is the restart.

- **Option A — status quo:** library residency is a start-time event.
  Growth stays an offline act; A1 untouched. Cost: a router reload per
  dictionary delivery (milliseconds; state is files).
- **Option B — load-on-first-reference:** an unknown structure id whose
  definition exists under lib/ is loaded resident at resolution time.
  The natural A4 reading (nothing resident unless demanded), and it
  makes dictionary distribution seamless. Cost: structure residency now
  changes at runtime, which reads against A1's "permanently resident,
  immutable" — the definition itself never mutates, but the set of
  resident things does.

**Recommendation: B, framed as an A1 clarification** (A1 fixes the
*universal* set and immutability of definitions; residency of
store-local promotions is an engineering property like router count).
NOT implemented — awaiting Jocke's ruling.

### 2.4 May a reference name into a container (packed layout)?

Reframed after Jocke's critique (2026-07-09, FRICTION #48): the model
never deleted the storage system — it RENTS one. "No store component"
delegates allocation, naming, lookup and durability to the filesystem,
and that subsidy holds only while the workload's natural unit is about
the filesystem's natural unit (a file). Phases 9–12 won because they
lived at file granularity. At record granularity the rent is ruinous —
an inode, dentry and 4 KiB block per 30-byte record (10× ingest, 20×
query vs the best conventional design, phase 14; phase 11's cold-read
gap, #41). Packing — many unsent instructions per container file,
references as names-with-offsets ("packs/7@4096") — is therefore not a
neutral optimization: it is the model re-importing a small store
component (an allocator) below the granularity where ext4's can be
rented. What would NOT come back: schemas, formats, parsers,
serializers, WALs — the container holds instructions, and only firing
interprets them. The axiom's honest form: "storage needs no SECOND
system, and no first one above file granularity."

- **Option A — status quo:** a reference is a file path, full stop.
  Purest reading; fine for file-granular work; IOPS tax stands.
- **Option B — packed containers:** a reference may name a container
  and a position. Spec §2 calls a reference "a name, nothing more —
  equivalent role to a file path today"; an offset-qualified name is
  arguably still just a name (files ARE offset ranges on a device), and
  demand semantics are unchanged. Needs the world-side passes
  (condense/compact/sync) taught to read and write containers.

**Recommendation: B, framed as world-layout engineering** (the grammar
and library never see it; only reference resolution does). NOT
implemented — awaiting Jocke's ruling.

### 2.3 Remote references (noted, not needed, not designed)

Phase 5 never needed a demand to cross the wire: the sender ships and
the receiver fires locally. A reference that names another node's world
would be a structural extension the spec is silent on. No option
analysis until a workload actually demands it.
