# Friction Log

Every place the model fought back (build brief, measurement 4). Each entry
says what happened, why, and whether it reads as a model flaw or a habit
flaw.

## 1. The error channel doesn't exist

The spec says malformed input is *unexpressible, not rejected* (§4). Two
cases forced a decision anyway:

- **Bytes that select no grammar rule** (bad tag): genuinely unexpressible —
  the router ends the stream carrying them. Clean, no friction.
- **A well-formed firing that fails at the edge** (missing file, unknown
  structure ID, reference escaping the root): something must return to the
  demander, and the model has no distinguished error form. The prototype
  returns a literal value beginning `ERR: `, which is indistinguishable
  from content that happens to start with `ERR: `.

Verdict: **model gap, small but real.** Inside the model errors are
unexpressible by construction, but terminals touch a world that can say no,
and the spec's edge story (§2 "Terminal structure") doesn't yet say what
comes back when the world refuses. Wants a decision at spec level, not
runtime level.

## 2. First contact with a missing reference

Posting reads the current content first (`eval(read(ref))`), so posting to
a reference that doesn't exist yet fails. Convention reaches for
create-on-write or an `if-missing` conditional. The model's answer turned
out to be: establishing a board/thread is an *explicit* instruction
(`write(ref, quote(""))`), exactly like `mkdir` today.

Verdict: **habit flaw.** Felt like friction for about five minutes, then
felt like the filesystem behavior everyone already accepts. No structure
was added.

## 3. Terminal writes reintroduce ordering at the edge — and the spec's own atomicity absorbs it

Post is read-append-write. Two simultaneous posts to one thread would be a
lost-update race *at the disk edge* — "nothing is written" holds inside the
model, but `write-file` is precisely the point where A2 stops. What saves
it: post is composed as **one instruction**, and the spec says an
instruction fires whole and indivisibly (§2). With one router, firings
serialize and the race is unexpressible.

But: the spec also says router count/placement is pure engineering, "any
topology works" (§2 Router). Two routers over the same disk root would race
their terminals. So topology freedom is unconditional only for pure
firings; **terminals bind their references to a router**, or edge writes
need something the model currently deletes.

Verdict: **model boundary, worth a spec sentence.** Not a flaw inside the
model — the "no cell to clobber" argument is airtight up to the terminal —
but §2's "any topology works" overstates once terminals share a target.

## 4. The demander must send bytes it just received back through the wire

Post embeds `eval(read(ref))` *inside* the instruction, so the
read-append-write travels as one indivisible tree — good. But a client that
first *reads* a thread and then wants to post something derived from what
it read has no way to refer to "what you just gave me"; it must ship the
content back inside the next instruction as a literal. With no store, there
is no handle to point at. This is the model being honest (values only in
flight), but it means conversational workloads pay round-trip content
weight unless they compose everything into single trees.

Verdict: **model property, not flaw — but it shapes style hard.** The
pressure is always toward bigger composition trees and away from
client-side logic between demands. That pressure felt correct for this
workload; unclear how it scales.

## 5. Measurement instrumentation wanted to be a store

The brief's repetition metric needs firing counts, which is state
accumulating across firings — exactly what the model deletes. It lives in
the router as an append-only log file, flagged as non-model
instrumentation. Noted because it was the only moment the *runtime* itself
was tempted to hold state, and the temptation came from observability, not
from the workload.

Verdict: **habit flaw / tooling question.** Observability of a model with
no state is its own topic; deferred like security.

## Not friction (things that just worked)

- **Thread index without a lookup subsystem**: the index is a thread. Same
  five structures maintain it. The queue-becomes-store failure mode (brief
  step 5) never appeared.
- **Persistence**: a thread file is literally `0x00 <len> <content>` — an
  unsent instruction. Restart recovery is *reading files*, there is nothing
  else to recover.
- **Self-delimiting instructions**: no framing protocol on the wire in
  either direction; outputs return quoted, so both directions carry only
  the one representation. The serialization deletion (§4) survived contact
  with sockets.
- **Determinism discipline**: timestamps enter as values composed by the
  demander. At no point did a structure want a clock.
