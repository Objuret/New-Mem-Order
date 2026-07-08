# Prototype Report — Message Board on the Activation Model

Answers the brief's four measurements and the spec's §6 question for one
real (small) workload. Numbers below are from the demo run of 2026-07-08
(`python3 demo.py`, then `python3 report.py` to regenerate them —
timestamps and ids will differ, shapes and counts will not).

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

## Reproducing

```
python3 demo.py     # runs router + two clients, restart, assertions
python3 report.py   # regenerates measurements 2 and 3 from the run
```
