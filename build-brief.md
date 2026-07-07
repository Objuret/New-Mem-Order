# Build Brief — Activation Model Prototype

Companion to `activation-model.md`. That file is the spec and is authoritative. This file says what to build, in what order, and what counts as done. Where this brief and the spec conflict, the spec wins.

---

## Objective

Build a minimal runtime implementing the four axioms, then run one real workload on it to answer the spec's §6 claim: how many structures does real work actually need?

This is a falsification prototype, not a product. Speed is irrelevant until the shape is proven. Code quality bar: readable and correct, nothing more.

## Scope choices — CONFIRM WITH JOCKE BEFORE CODING

- **Language**: [Python to falsify shape fast | Rust for real perf data from day one]. Not decided. Ask.
- **Test workload**: [key-value store | message board | other small-but-real target]. Not decided. Ask. Requirement on whatever is picked: it must involve persistence across restart and at least two clients interacting, so A2/A4 get genuinely exercised — a pure calculator proves nothing.

Do not decide these yourself. Do not decide anything else structural on Jocke's behalf either — when the spec is silent and the choice is architectural, present options and wait.

## Build order

**1. Instruction format.**
Compact binary: structure IDs + values + wiring, nested composition trees (spec §2). One encoder, one decoder. This format is simultaneously file format, wire format, execution format — build it once, use it everywhere, never introduce a second representation. If you catch yourself writing a converter between two representations, stop: that's the spec's serialization deletion being violated.

**2. Structure library.**
Start EMPTY. Add structures only when the workload forces them. Every structure: immutable after load, deterministic (same values in = same result out, always — no clock reads, no randomness, no I/O inside non-terminal structures). Keep a running log: structure name, why the workload forced it, date added. This log is the primary experimental output of the whole project.

**3. Router.**
One event loop. Receive instruction → resolve IDs → fire whole tree → return output to demander. No overlap checking, no locks, no coordination machinery — the spec deletes these; if a race appears to exist, the bug is a hidden write somewhere, not missing locks. Find the write and delete it.

**4. Terminals.**
Thin syscall wrappers: write-fd, socket-send, read-fd as demand. These are the only structures allowed side effects. Mark them explicitly in the library log.

**5. Persistence = files.**
No database, no store, no index component. Unsent instructions are files; a reference is a path; demanding = reading = firing. State surviving restart must work exactly this way. If the workload seems to need "find the current X," the answer is: the demander holds the reference — not a lookup subsystem. If that ever feels impossible rather than just unfamiliar, STOP and report it as a finding instead of building around it — that would be the queue-becomes-store failure mode, and detecting it is a valid experimental result.

**6. Workload on top.**
Implement the chosen workload purely as instructions over the library. No escape hatch into ordinary code for the workload logic. Where the model makes something awkward, write the awkwardness down — do not silently patch the runtime.

## Measurements (deliverable)

1. **Structure count**: total structures the workload forced, from the library log. The §6 number.
2. **Repetition**: distinct structure-compositions fired vs. total firings.
3. **Instruction size**: bytes on wire/disk in activation form vs. a naive JSON equivalent of the same operations.
4. **Friction log**: every place the model fought back — what, why, whether it's a model flaw or a habit flaw.

## Done means

Workload runs, survives restart via files-as-unsent-instructions, two clients interact through the router, and the four measurements exist in a short report. No performance targets.

## Hard rules

- The spec's deletions are load-bearing. Do not reintroduce: parsing layers, serialization converters, locks, a store/index component, mutable state outside terminals. Reintroducing one silently invalidates the experiment.
- Nothing varies inside a structure. Time, randomness, input — all arrive as values in instructions.
- When blocked between the model and convention, the model wins until it demonstrably can't — and "demonstrably can't" goes in the friction log as a result, not a workaround.
