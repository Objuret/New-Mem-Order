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
