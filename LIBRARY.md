# Structure Library Log

The running log required by build-brief step 2: every structure, why the
workload forced it, when. This is the primary experimental output of the
project. The library started empty; entries appear here in the order the
message-board workload forced them. `am/structures.py` and this file must
not drift.

## Library structures

| ID | Structure | Kind | Forced by | Date |
|----|-----------|------|-----------|------|
| 1 | `concat` | pure | Rendering a thread: a message must join the output of its chain (the demanded previous message) with its own fields. Also the only way to put two terminal emits inside one indivisible firing (see FRICTION.md #3). | 2026-07-08 |
| 2 | `emit-disk` | **TERMINAL** | Posting: a message must come to rest in the world as an unsent instruction file, and the thread-head reference file must be replaced to name it. The only structure with side effects. Binds to the single router (spec §2, Terminal structure). | 2026-07-08 |
| 3 | `select` | pure | Phase-2 query (a), find posts containing a value: filter-shaped computation `concat` cannot absorb. Keeps the segments of a value that contain a needle; the delimiter and needle are both comparison operands (values), so the record convention stays in the world, not the library. | 2026-07-08 |
| 4 | `tally` | pure | Phase-2 query (b), count posts per user: fold-shaped counting. Counts segments containing a needle; emits the count as decimal ASCII (the library's one number convention — FRICTION.md #11). Condition is a value. | 2026-07-08 |
| 5 | `last` | pure | Phase-2 query (c), N newest posts: positional selection. Returns the last N segments; N enters as a decimal-ASCII value. | 2026-07-08 |
| 6 | `sum` | pure | Phase-4 ledger totals: additive fold over numeric segments. First arithmetic in the library. | 2026-07-09 |
| 7 | `sort` | pure | Phase-4 sorted listings: reordering, which no composition of existing structures can express. Mode (`num`/`text`, `±desc`) is a value. | 2026-07-09 |
| 8 | `div` | pure | Phase-4 averages: scalar division (avg = div∘(sum, tally) — composed, no avg structure). Division by zero refuses. | 2026-07-09 |
| 9 | `sub` | pure | Phase-4 remaining-budget: scalar subtraction across two demanded chains (the join-shape is composed by the demander, not a structure). | 2026-07-09 |
| 10 | `pick` | pure | Phase-4 threshold filter: `select` matches by containment, not magnitude. Comparator and threshold are values. | 2026-07-09 |
| 11 | `uniq` | pure | Phase-8 open-key grouping: extracting the key set from a write-side projection chain (`uniq∘sort`). Adjacent-duplicate fold; delimiter is a value. | 2026-07-09 |

## Grammar nodes used

Counted alongside library structures per spec §6 — relocating capability
into the grammar must not shrink the headline number.

| Node | Used for |
|------|----------|
| literal | every value: message text, users, timestamps, references-as-values, instruction-bytes-as-values |
| composition | every structure invocation |
| demand | reading = running: firing the head file, firing the message chain, persistence |
| error | refusals: missing reference, cyclic demand, malformed/truncated bytes, wrong arity |

## Headline §6 count — growth curve

| after | library structures | grammar nodes | total |
|---|---|---|---|
| phase 1 (message board) | 2 (1 pure + 1 terminal) | 4 | 6 |
| phase 2 (computation pressure) | 5 (4 pure + 1 terminal) | 4 | **9** |
| phase 3 (the layer, real content) | 10 (5 universal + 5 promoted templates) | 4 | **14** |
| phase 4 (arithmetic + shapes) | 17 (10 universal + 5 templates + 2 shapes) | 4 | **21** |
| phase 8 (open-key grouping) | 18 (11 universal + 5 templates + 2 shapes) | 4 | **22** |

Phase 2 grew the library by exactly the three query shapes (filter, fold,
positional take), all pure, all with conditions as values. No grammar
node was added in any phase.

Phase 3 grew it by 5 promoted content templates (admission log below):
zero-operand pure structures whose definitions are unsent literal
instructions under `store/lib/<sid>`, loaded resident at mount. **The
library hit the charter's ~10 reporting threshold exactly** — reported
as a finding, not a failure, in REPORT.md, together with the observation
that promoted templates are store-local (data-derived), not universal:
the count now has two tiers, 5 universal + N-per-store.

## Structures considered and NOT added

- `socket-send` (terminal): the brief lists it as an expected terminal, but
  the workload never forced it — returning output to the demander is the
  demand return path (router mechanics, spec §2 Output), not a structure.
- `read-file`: forbidden by brief step 4; demanding covers it.
- `seq`: sequencing two emits was covered by `concat`; adding a
  dedicated sequencer was not forced (noted as friction instead).
- any constructor of instruction bytes from values (`make-demand-node`):
  would close the post race (FRICTION.md #2) but edges toward computed
  demand references; ruled to stay open by design (DECISIONS.md §2.1).
- `group-by` / key-extraction (phase 2): "count posts per user" for an
  UNKNOWN user set would need a structure that extracts keys between
  format markers — a resident parser. Refused; the demander supplies the
  user set instead (FRICTION.md #10). **Resolved in phase 8 without a
  parser**: the writer stores an authors projection chain, the key set
  becomes a query (`uniq∘sort`), grouping composes as before (#34).
- `count-lines`: `tally` with the needle every segment contains would
  cover it; never separately forced.
- `max` / `min` / `avg` / `count-over` / `top-N` / `join` (phase 4): all
  composed from existing structures — see the table below.

## Computed by composition, NOT added (phase 4 — the flattening evidence)

Eight workload computations needed zero new structures:

| computation | composition |
|---|---|
| max | `last(sort(x, num), 1)` |
| min | `last(sort(x, numdesc), 1)` |
| average | `div(sum(x), tally(x, ""))` |
| count | `tally(x, "")` |
| count over threshold | `tally(pick(x, ge, t), "")` |
| top-N | `last(sort(x, mode), N)` |
| posts-by-user over the board | `select(demand(thread), "] user: ")` |
| remaining budget (join-shape) | `sub(demand(budget), sum(demand(ledger)))` |

Five structures in, eight computations composed out — universal growth
went sub-linear in workload items for the first time.

### Condensation pass admissions (2026-07-08)

| sid | block bytes | files | hits | bytes saved | example files |
|---|---|---|---|---|---|
| 100 | 546 | 5 | 9801 | 5350800 | fidelity/text-204800, fidelity/text-4095, fidelity/text-4096, fidelity/text-4097 |
| 101 | 1068 | 30 | 30 | 30972 | repo/src/mod_00.py, repo/src/mod_01.py, repo/src/mod_02.py, repo/src/mod_03.py |
| 102 | 631 | 30 | 30 | 18299 | repo/src/mod_00.py, repo/src/mod_01.py, repo/src/mod_02.py, repo/src/mod_03.py |
| 103 | 523 | 5 | 5 | 2092 | fidelity/text-204800, fidelity/text-4095, fidelity/text-4096, fidelity/text-4097 |
| 104 | 663 | 3 | 3 | 1326 | repo/CONTRIBUTING.md, repo/README.md, repo/docs/guide.md |

Rejected: 0 recurring blocks seen in only 2 files; 80 admitted-block occurrences unreplaceable because they span stored chunk boundaries (fixed 64 KiB boundaries -- charter's noted caveat).

### Shape-condensation pass admissions (2026-07-09)

| sid | shape | instances | operand slots | folded const bytes/inst | example files |
|---|---|---|---|---|---|
| 100 | `C1(D,L,L)` | 9 | 2 | 1 | amts/alice-0, amts/alice-1, amts/alice-2 |
| 101 | `C1(D,L,L,L,L,L,L,L)` | 3 | 3 | 22 | msgs/1783597745001-alice, msgs/1783597745033-bob, msgs/1783597745066-carol |

## Phase 19 — computation pressure (2026-07-11, Jocke's charter)

Ten diverse computation tasks (aggregation, order statistics, text
analytics, bucketing, per-element transformation, weighted reduction),
compose-first. Eight of ten composed from the existing tier. Two
structures and one op-vocabulary extension were forced:

| sid | name | signature | forced by | why composition failed |
|---|---|---|---|---|
| 12 | `replace` | (value, old, new) — pure | task 7 (top-3 words) | segment ops see ONE delimiter; free text mixes two ("\n" and " "); no composition changes bytes inside segments |
| 13 | `scale` | (value, delim, factor) — pure | task 9 (amounts ×k) | per-element arithmetic has no composition; a generic per-element apply would fire sub-instructions (eval — forbidden), so the verb enters as one fixed pure structure |
| — | `pick` ops `seq`/`sne` | vocabulary extension | task 7 | word counting needs whole-segment equality; select/tally are contains-based (friction #9: "the" must not match "theatre") |

Composed, NOT added (the flattening evidence, continued): mean
(div∘sum∘tally), median and p90 (double sort/last suffix trick —
element-at-index composes with no `first` structure), range
(sub∘sum∘last∘sort — sum-over-one-segment is the scalar-extraction
bridge for the terminator convention), histogram (nested pick),
count-over-threshold (tally∘pick), weighted total (write-side zip:
chain links hold scale compositions the model fires at render),
top-3 ranking (count-word pairing encoded as count×1000+index via
scale+sum, sorted numerically, decoded by the demander).

Growth curve: **11 → 13 universal (+1 vocabulary extension) for 10
computation tasks — sub-linear again.** Standing risk, stated plainly:
per-element VERBS are a linear axis (`scale` is verb #1; add-constant,
modulo, clamp would each cost one more). The §6 question under
computation pressure is now: how many per-element verbs does real work
need? Unanswered — that is the next falsification pressure.

Native-parity debt: sids 12–13 and the seq/sne ops exist in the Python
router only; amd/amx refuse them (disclosed, not yet implemented).
