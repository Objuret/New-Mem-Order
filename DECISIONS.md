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

---

## 2. Open structural questions for Jocke (NOT implemented)

### 2.1 Should posting be closable into one firing?

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
