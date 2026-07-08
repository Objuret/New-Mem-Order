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

## 7. What produced zero friction (worth recording)

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
