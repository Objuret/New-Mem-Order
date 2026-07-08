# Prototype Report — Message Board on the Activation Model

Answers the brief's four measurements and the spec's §6 question. Two
phases: phase 1 (the message board) and phase 2 (computation pressure:
queries over the phase-1 data). Numbers are from the demo run of
2026-07-08 (`python3 demo.py`, then `python3 report.py` to regenerate —
timestamps and ids will differ, shapes and counts will not). Phase-1
sections are kept as written; phase 2 is appended at the end with the
growth curve.

## What ran

A message board: one thread, two users (alice, bob), three posts and two
full reads through a single router, one refused read of a nonexistent
thread, one router restart in the middle. All workload logic is
instructions over the library; the client only constructs instructions
and displays outputs. The board survived the restart bit-for-bit with no
persistence code anywhere — the unsent instruction files under `world/`
are the only state that exists.

The shape the model gave the board: a message is an unsent instruction
`concat(demand(previous), ...fields)`; a thread head is a literal node
holding the newest message's reference at a fixed path; reading the
thread is demanding the head's value, which fires the entire chain —
reading is running, and the rendered thread is the output of the oldest
message's firing cascading forward. Posting is one indivisible firing
that emits the new message file and replaces the head file.

## Measurement 1 — structure count (the §6 number)

**2 library structures + 4 grammar nodes = 6.**

| | |
|---|---|
| `concat` | pure |
| `emit-disk` | terminal (the only side effect in the system) |
| literal, composition, demand, error | grammar nodes, counted per §6 |

Full log with forcing reasons: LIBRARY.md. Notable: no read structure
exists (demand covers persistence), no socket-send was forced (the
demand return path covers replies), and nothing that fires values was
needed — no §6 falsification event occurred.

## Measurement 2 — repetition

From `stats.log` (26 instruction firings = 13 wire arrivals + 13
demanded files):

- **distinct composition shapes: 4** across 26 firings, 98 grammar-node
  evaluations
- shapes: `D` (bare demand, ×9), `L` (head/genesis files, ×7),
  `C1(D,L,L,L,L,L,L,L)` (message files, ×6), `C1(C2(L,L),C2(L,L))`
  (post/new-thread, ×4)

Every operation the board performs — create, post, read, and even the
stored message files themselves — collapsed onto four shapes. The
post instruction and the new-thread instruction turned out to be the
same shape. This is the repetition §6 predicts, at toy scale.

## Measurement 3 — stored-form overhead

Grammar overhead of stored instructions over their content bytes
(content = literal payloads + demand references):

| stored instruction | file bytes | content bytes | overhead |
|---|---|---|---|
| message (typical, ~40-char text) | 104–108 | 85–89 | 19 |
| genesis | 25 | 23 | 2 |
| thread head | 26 | 24 | 2 |
| **whole world after demo** | **338** | **277** | **61 (18.0%)** |

Overhead is ~2 bytes per node (tag + length varint); a message costs a
flat 19 bytes of grammar regardless of text length, most of it the
per-field literal framing. No compression codec exists anywhere — the
compactness is references replacing repeated content (each message
carries the whole thread-so-far as a 20-odd-byte demand reference).

## Measurement 4 — friction

Full log: FRICTION.md. Two honest model edges (two-step reads through a
mutable-world indirection; a lost-update window on contended posts —
options for Jocke in DECISIONS.md §2.1), two habit-vs-model findings
(`concat` moonlighting as a sequencer; explicit genesis instead of
empty-as-absence), one engineering note (chain depth = recursion depth),
and a list of things that produced zero friction where convention
predicted plenty: no converters, no recovery code, no locks, no parse
errors.

## §6 verdict, honestly scoped

For this workload the claim held with room to spare: the library
saturated at two structures almost immediately and every subsequent
operation reused them. Values in flight did not balloon; the structure
set did not balloon. But this is one tiny workload chosen to be
model-friendly — the encouraging number is how early the library stopped
growing, not the absolute 6. The next falsification pressure should come
from a workload that wants computation (filtering, counting, comparing),
which `concat` cannot absorb.

---

# Phase 2 — computation pressure (2026-07-08)

The question ruled for this phase: how much does the library grow when a
workload demands computation `concat` cannot absorb? Three queries over
the existing board data, run in the demo *after* the router restart, so
they provably operate on nothing but the surviving files:

- **(a) find** posts containing a given value → `select(chain, "\n", needle)`
- **(b) count** posts per user → `concat` of one `tally(chain, "\n", "] user: ")` per user, the result table composed inside the instruction
- **(c) N newest** posts → `last(chain, "\n", N)`

Every condition — needle, delimiter, count — entered as a value, a
comparison operand. Nothing filter/fold-shaped ever needed to fire a
sub-instruction; the eval boundary was never approached. **No §6
falsification event.**

## The growth curve (measurement 1, updated)

| after | library | grammar | total |
|---|---|---|---|
| phase 1 | 2 (1 pure + 1 terminal) | 4 | 6 |
| phase 2 | 5 (4 pure + 1 terminal) | 4 | **9** |

Growth was +3, exactly one structure per query shape (filter, fold,
positional take), all pure. The ~10-structure reporting threshold was
not crossed, though 9 is close enough to note: each genuinely new
*computation shape* seems to cost one structure. The counter-observation
is that all three took the same operand form (value, delimiter,
condition) and composed with the existing library on first contact — the
`count` result table is plain `concat` over `tally` outputs.

## Repetition (measurement 2, updated)

Full demo including phase 2: **62 instruction firings, 7 distinct
composition shapes**, 305 grammar-node evaluations. New shapes:
`C3(D,L,L)` (find, ×2), `C5(D,L,L)` (newest), and the one-firing
per-user table `C1(L,C4(D,L,L),L, ×3 users)`. Message-file firings rose
from 6 to 24 — the per-user count re-demands the chain once per tally,
because the grammar is a tree with no way to bind a value once
(FRICTION.md #13).

## Stored-form overhead (measurement 3, unchanged)

Queries left the world byte-identical: 338 stored bytes, 18.0% grammar
overhead, exactly as after phase 1. A query is an instruction that
borrows the chain's firing and vanishes — no index, no cache, no
materialized view came into existence.

## Friction (measurement 4)

Six new entries, FRICTION.md #8–#13. The central finding (#8): the
stored chain fires to one thing only — the rendered thread — so queries
compute over the render and inherit its convention (spoofable markers,
#9). The model never needed a parser, but field-precise querying would
require a different *stored* chain shape, not more query machinery.
Secondary findings: open-key grouping would need a resident parser
(refused, demander supplies the keys, #10); computation forced a shared
number convention, decimal ASCII (#11); and the tree-not-DAG cost above
(#13).

## §6 verdict after phase 2

The claim still stands, with its first real price tags visible. The
library grew linearly with new computation shapes (not with data, users,
or queries run), conditions-as-values held everywhere, and querying
added zero resident or resting state. The pressure that phase 2 exposes
for a phase 3 is: field-precise access (stored-shape evolution),
open-key grouping, and whether shape-per-computation growth flattens
into reuse as workloads accumulate — the §6 bet is that it does.

## Reproducing

```
python3 demo.py     # board + restart + refusals + the three queries
python3 report.py   # regenerates measurements 2 and 3 from the run
```
