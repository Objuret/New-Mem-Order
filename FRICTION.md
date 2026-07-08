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
