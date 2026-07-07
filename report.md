# Report — Activation Model Prototype, Run 1

Workload: message board (chosen per brief). Two clients post and read
through one router; the board survives a router restart with no store
component — threads are plain files whose bytes are unsent instructions.
Language: Python (chosen per brief — falsify shape fast).

All numbers below are from `python3 demo.py` on 2026-07-07 and are
reproducible with that command.

## Done-means checklist

- ✅ Workload runs (create board, create thread, post, read, list threads)
- ✅ Survives restart via files-as-unsent-instructions (a thread file is
  `0x00 <varint len> <content>` — firing it yields the thread)
- ✅ Two clients interact through the router (alice and bob, concurrent
  connections; bob reads alice's post, alice reads bob's reply)
- ✅ Four measurements below

## 1. Structure count — the §6 number

**5 structures** covered the entire workload. Three pure (`concat`,
`quote`, `eval`), two terminals (`read-file`, `write-file`). Full
rationale per structure in `structure-log.md`, including three candidates
considered and rejected. The library was grown strictly on demand from
empty, per the brief.

## 2. Repetition

**4 distinct compositions / 10 top-level firings / 35 structure
invocations** in the demo run:

| fired | composition (structure IDs, `·` = value) | meaning |
|---|---|---|
| 5× | `3(4(·))` | read a reference (thread, index) |
| 3× | `5(·,2(1(3(4(·)),·)))` | post: read-append-write, one indivisible tree |
| 1× | `5(·,2(·))` | establish board (write empty index) |
| 1× | `1(5(·,2(·)),5(·,2(1(3(4(·)),·))))` | create thread: two writes as one series |

Even in a run this small, repetition dominates: the top two shapes are 80%
of all firings. The claim that real work is few compositions fired often
is *consistent with* this run — but a 10-firing demo can't carry the §6
claim alone; it needs a longer trace.

## 3. Instruction size vs naive JSON

| operation | activation form | naive JSON equivalent |
|---|---|---|
| post ("hi alice", thread `general`) | **76 B** | 102 B |
| read thread | **17 B** | 35 B |

The activation post is smaller than the JSON *even though it carries the
whole read-append-write program*, because program structure costs 1–3
bytes per node while JSON pays for field names and syntax. Stored thread
file: 2 B of instruction overhead over raw content (128 B holding 126 B) —
the "file is already an unsent instruction" story costs almost nothing.

Caveat: the JSON baseline assumes a smart server that already contains the
board logic; activation moves that logic into the wire as references. At
these sizes references undercut field names. Entropy-dense values would
ride as literals in both forms (spec §7) and the gap would close toward
zero, never invert structurally.

## 4. Friction log

See `friction-log.md`. Headline findings:

1. **Error channel is a real spec gap**: terminals touch a world that can
   refuse, and the model has no distinguished form for what returns then.
2. **"Any topology works" needs one qualifier**: it's unconditional for
   pure firings, but terminals sharing a disk target bind ordering to a
   router. The spec's own fires-whole atomicity covers the single-router
   case exactly.
3. Everything else that felt like friction turned out to be habit
   (explicit board bootstrap ≈ mkdir), and the predicted failure mode —
   queue-becomes-store — never appeared: the thread index stayed an
   ordinary thread.

## Verdict on this run

The four deletions held under contact with a real (small) workload: no
parser, no serializer, no locks, no store component exists anywhere in the
runtime. The §6 count came out **5**, far under any ballooning scenario,
with repetition already dominant at trivial scale. The two items worth
taking back to the spec are the error channel and the terminal-topology
qualifier — both edge phenomena, both at exactly the boundary the spec
already flags as its honest edge (§7).
