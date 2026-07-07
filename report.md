# Report — Activation Model Prototype, Run 2

Workload: message board (chosen per brief). Two clients post and read
through one router; the board survives a router restart with no store
*component* — threads are plain files whose bytes are unsent instructions.
Language: Python (chosen per brief — falsify shape fast).

Run 1 (five structures, including `eval`) was reviewed and its headline
number rejected: `eval` fires arbitrary in-flight bytes, quote+eval is a
universal interpreter, and a library containing one keeps the §6 count
flat for any workload forever — the measurement was disabled, not
confirmed. Run 2 is the rebuild after that finding: `eval` is gone,
demand-by-reference moved into the instruction grammar where spec §3.1/A4
put it, `read-file` proved subsumed by it, and errors got a reserved form.
Details in friction-log.md #6 and spec-amendments.md. All numbers below
are from `python3 demo.py` on 2026-07-07, reproducible with that command.

## Done-means checklist

- ✅ Workload runs (create board, create thread, post, read, list threads)
- ✅ Survives restart via files-as-unsent-instructions (a thread file is
  `0x00 <varint len> <content>` — firing it yields the thread)
- ✅ Two clients interact through the router (alice and bob, concurrent
  connections; bob reads alice's post, alice reads bob's reply)
- ✅ Four measurements below

## 1. Structure count — the §6 number

**3 structures**: `concat`, `quote`, and the one terminal `write-file`.
Grown strictly on demand from empty; per-structure rationale, the two
run-2 removals, and four rejected candidates in `structure-log.md`.

What makes 3 a *usable* number where run 1's 5 was not: nothing in this
library can fire bytes. Complexity can no longer hide in values-in-flight;
to run, it must become a stored instruction behind a reference —
`write-file` then demand — which is visible, countable, and exactly the
model's own definition of a program. Standing rule going forward: nothing
that fires values ever enters the library; a workload that seems to need
that is a §6 falsification event and gets reported, not implemented.

## 2. Repetition

**4 distinct compositions / 10 top-level firings / 17 structure
invocations** in the demo run (`D` = demand node, `·` = value):

| fired | composition | meaning |
|---|---|---|
| 5× | `D` | read a reference (thread, index) — a bare demand |
| 3× | `3(·,2(1(D,·)))` | post: read-append-write, one indivisible tree |
| 1× | `3(·,2(·))` | establish board (write empty index) |
| 1× | `1(3(·,2(·)),3(·,2(1(D,·))))` | create thread: two writes as one series |

The top two shapes are 80% of all firings. Consistent with §6's
few-compositions-fired-often claim — but a 10-firing demo cannot carry
that claim; it needs a longer trace and a second workload sharing this
library.

## 3. Instruction size vs naive JSON — anecdote, not evidence

Recorded because the brief asks; at n=1 with toy payloads this comparison
is apples-to-oranges (the JSON baseline presumes a server already
containing the board logic) and should not be argued from:

| operation | activation form | naive JSON equivalent |
|---|---|---|
| post ("hi alice", thread `general`) | 70 B | 102 B |
| read thread | 11 B | 35 B |

One number here *is* structural rather than anecdotal: a stored thread
file carries **2 B** of instruction overhead over its raw content (128 B
holding 126 B) — "a file is already an unsent instruction" costs
essentially nothing.

## 4. Friction log

See `friction-log.md` — six entries, three now with run-2 resolutions.
Headlines:

1. **`eval` was a builder flaw the review caught** (#6): the workload,
   pressed, needed strictly less than a universal interpreter — every
   run-1 eval was really a demand of a stored literal. Model vindicated
   on the evidence; measurement re-enabled.
2. **Errors now have a reserved form** (#1): a firing returns a value or
   an error, distinguishable by construction; refusals abort the whole
   indivisible firing and propagate. Spec wording proposed
   (spec-amendments.md #2), awaiting Jocke.
3. **The mutation moved; it didn't die** (#3): the model did not
   eliminate the store — it shrank it to the filesystem edge and fenced
   it behind fires-whole atomicity, with races structurally confined to
   terminals. One router serializing terminals is load-bearing; "any
   topology works" needs the qualifier proposed in spec-amendments.md #3.

## Verdict on this run

The deletions held where the spec claims them: no parser, no serializer,
no locks, no store *component* anywhere in the runtime — while the honest
accounting is that statefulness lives at the terminal edge, fenced, not
abolished. The §6 count from a library with no universal structure in it
is **3**, with repetition already dominant at trivial scale. Three spec
amendments are drafted and waiting on Jocke (spec-amendments.md); the
prototype implements all three so rejection means reverting code, not just
text. Next experiment that would actually move the claim: a second, larger
workload over the *same* 3-structure library, watching whether the library
grows linearly with workloads (falsification) or sublinearly (support).
