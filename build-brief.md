# Build Brief — Activation Model Prototype

Companion to `activation-model.md`. That file is the spec and is authoritative. This file says what to build, in what order, and what counts as done. Where this brief and the spec conflict, the spec wins.

---

## Objective

The concept being tested is spec §0 — read all of it; the goals there override any summary. Build a minimal runtime implementing the four axioms, then run one real workload on it to answer the spec's §6 claim: how many structures does real work actually need?

This is a falsification prototype, not a product. Speed is irrelevant until the shape is proven. Code quality bar: readable and correct, nothing more.

## Scope — decided, do not revisit

- **Language**: Python. Falsification prototype; speed irrelevant.
- **Test workload**: message board. Post messages, read a thread, minimum two users. Must survive restart (persistence via files-as-unsent-instructions) and support two clients interacting through the router.

Anything else structural where the spec is silent: present options to Jocke and wait. Do not decide on his behalf. If asking is blocked (tool failure, no interactive channel): STOP, write the options and your recommendation to DECISIONS.md, and end the session there. Never implement the recommendation, even reversibly.

## Build order

**1. Instruction format.**
Compact binary: structure IDs + values + wiring, nested composition trees, plus the demand and error grammar nodes (spec §2). Self-delimiting; no decode-to-tree step exists — firing walks the bytes directly. One encoder for construction; nothing that materializes a second representation. If you catch yourself writing a converter between two representations, stop: that's the spec's serialization deletion being violated.

**2. Structure library.**
Start EMPTY. Add structures only when the workload forces them. Every structure: immutable after load, deterministic (same values in = same result out, always — no clock reads, no randomness, no I/O inside non-terminal structures). Keep a running log: structure name, why the workload forced it, date added. This log is the primary experimental output of the whole project.

**3. Router.**
One event loop. Receive instruction → resolve IDs → fire whole tree → return output to demander. No overlap checking, no locks, no coordination machinery — the spec deletes these; if a race appears to exist, the bug is a hidden write somewhere, not missing locks. Find the write and delete it.

**4. Terminals.**
Thin syscall wrappers for output to the world: write-fd, socket-send. These are the only structures allowed side effects. Mark them explicitly in the library log. Reading stored instructions is NOT a terminal — that is the demand grammar node (spec §2), which fires the referenced instruction; no read-file structure belongs in the library. Terminals touching shared world-state bind to exactly one router (spec §2, Terminal structure).

**5. Persistence = files.**
No database, no store, no index component. Unsent instructions are files; a reference is a path; demanding = reading = firing. State surviving restart must work exactly this way. If the workload seems to need "find the current X," the answer is: the demander holds the reference — not a lookup subsystem. If that ever feels impossible rather than just unfamiliar, STOP and report it as a finding instead of building around it — that would be the queue-becomes-store failure mode, and detecting it is a valid experimental result.

**6. Workload on top: the message board.**
Post message, read thread, two users — implemented purely as instructions over the library. A "thread" is whatever the model makes it (likely a chain of unsent instructions referenced by demanders) — discovering that shape IS the experiment. No escape hatch into ordinary code for the workload logic. Where the model makes something awkward, write the awkwardness down — do not silently patch the runtime.

## Measurements (deliverable)

1. **Structure count**: total library structures the workload forced, from the library log, reported alongside the grammar node count. Relocating capability from library to grammar must not shrink the headline number. This is the §6 number.
2. **Repetition**: distinct structure-compositions fired vs. total firings.
3. **Stored-form overhead**: bytes of a stored instruction over its raw content. (Comparisons to JSON or other formats: optional, labeled anecdote only.)
4. **Friction log**: every place the model fought back — what, why, whether it's a model flaw or a habit flaw.

## Done means

Message board runs, survives restart via files-as-unsent-instructions, two clients post and read through the router, and the four measurements exist in a short report. No performance targets.

## Hard rules

- The spec's deletions are load-bearing. Do not reintroduce: parsing layers, serialization converters, locks, a store/index component, mutable state outside terminals. Reintroducing one silently invalidates the experiment.
- Nothing that fires values ever enters the library — no eval, no apply, no universal interpreter. A workload that seems to need one is a §6 falsification event: reported, not implemented.
- Nothing varies inside a structure. Time, randomness, input — all arrive as values in instructions.
- When blocked between the model and convention, the model wins until it demonstrably can't — and "demonstrably can't" goes in the friction log as a result, not a workaround.
