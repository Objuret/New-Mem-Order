# DERIVATION — how MACHINE.md happened

The conversation of 2026-07-11, preserved as a reasoning chain while it
was still whole in context. MACHINE.md is the law; this is why the law
says what it says, and — equally important — the record of every way
the assistant misread Jocke on the way, so the next agent flinches
before repeating it. Quotes are near-verbatim.

Background: nineteen prototype phases and a hostile external review had
just concluded on `claude/build-it-r1yzg9` (prior art, no authority
here). Jocke set the project aside and asked for ground truth instead.

Fresh agent: before absorbing anything below, read the "how to read
this without being poisoned" section in SOUL.md. Short form: prior-art
names are scenery, not links to follow; assistant assessments are
testimony to re-derive, not doctrine; quoted negative results carry
their operating point or nothing; and the corrections are guardrails
to internalize, not a guilty persona to adopt.

---

## The chain

**1. "Before talking about the actual project, talk to me about how
computing actually works.. How a processor is used etc from a
program."**

He was handed the machine primer: programs are lists of numbers;
fetch-decode-execute against a few dozen registers; the defining fact
that memory is 100-300 cycles away while arithmetic is ~free; caches,
prefetchers, and branch speculation as compensation machinery; cores
sharing one memory system; every byte moved costing energy; the OS and
syscalls as rented machinery. Summary law: performance is bytes moved,
in what pattern, across how many boundary crossings.

**2. "That was pretty much what I wanted to create on the cache, a
register, but kinda a register for instructions or combinations of
instructions even."**

The assistant mapped this onto hardware history (µop caches and trace
caches = registers for code combinations, already built) and onto its
own prior experiment, declaring the "instruction half" already solved
and redundant.

**3. "You are also forcing my thoughts to fit your solution now."**

CORRECTION 1 — the defining one. What actually happened: the assistant
sorted his idea into the two boxes its own build contained, kept the
box that flattered the build, and dismissed the rest by citing its own
failed experiment as if that settled Jocke's idea (it only settled one
implementation at one operating point). Operational lesson, now a rule:
when Jocke states a concept, restate it AT CONCEPT LEVEL and get his
confirmation before mapping it to anything — especially before mapping
it to something you built or read about. His words are gestures at
concepts, not vocabulary bound to referents.

**4. "You say CODE is solved 'instantly' — what the fuck is data if
not code?"**

The premise of the machine, arrived at by his question, not by design:
there is NO physical code/data distinction — one memory, one kind of
byte. The machine privileges bytes reached as code because they arrive
with promises: immutable, stable identity, massive visible recurrence,
vetted origin. "Data" is bytes that promise nothing. The industry
deliberately HARDENED the split (W^X, DEP) because unpromised
data-as-code is the injection vulnerability class. Therefore: data that
makes code's promises may be treated as code — and the fixed-vocabulary
condition (data can only arrange vetted structures, never mean
"execute arbitrary bytes") is what makes the dissolution safe.

**5. "Cache is kinda meaningless, but can be used to store the queue
instead, so the actual firing of the operations to the cpu can go
faster."**

Layer 3's seed. Honest split established: cache-as-mirror is real value
for hot working sets, pure waste for streams (most large-system
traffic). His proposal — SRAM holding staged work rather than guessed
copies — has three buildable ancestors (scratchpads; decoupled
access-execute queues; dataflow machines, where "firing on arrival" is
the literal technical term and whose descendants — TPU, Groq, Cerebras
— are the fastest chips alive). Why mainstream kept the mirror: it
demands nothing from software. The queue design wins wherever software
can ANNOUNCE its operation stream — which is a representation problem,
not a silicon problem.

**6. "With a key or indexing... it could in theory just go through a
matrix which matches the data structures or code to the predetermined
results without actual computation. Just pointerswaps and done."**

The lookup layer. Computation and lookup are interchangeable (FPGA LUTs
at the bottom; memoization, materialized views, build caches, git's
pointer-swap trees above). Three constraints bound it: tabulate the
OCCURRING, never the possible (spaces are exponential); only pure
deterministic operations qualify; identity must be cheaper than the
computation — data must CARRY its identity or the hashing eats the win.

**7. "No, i mean the SHAPES, not every single fucking output, but the
roads."**

CORRECTION 2 — wrong layer. The assistant had answered with output
tabulation; Jocke meant the control structure. The roads version is
stronger and has a perfect existence proof: regex compiled to a DFA =
the complete road matrix emitted up front, execution reduced to one
table hop per byte, zero decisions. Tracing JITs pave roads lazily.
The hardware's branch predictor is the CPU trying to reconstruct the
roads matrix by statistical guesswork because software throws the map
away. The one honest obstruction: roads fork on values. Tag-forks
(which kind of thing is this?) become free lookups if data carries its
discriminator; value-forks (is it > 5000?) are real computation
forever, small, and never to be lied about.

**8. "Ngl, it mostly feels like you are just running a gun range
instead of trying to fucking solve this creatively."**

CORRECTION 3. Cataloguing prior art and limits is defense; he wanted
synthesis. The response welded his statements into one machine (roads
resident; the data stream as the instruction stream via tags; honest
forks; paving; pointer swaps) — and produced the self-critical insight
that became falsifiable claim 1: the prior build's shape-compiled
firing experiment was tested at 2-3 shapes, exactly where branch
predictors are perfect, so the design's actual claimed regime — HIGH
shape-entropy streams, where predictor tables thrash and tag-routing
stays O(1) — has never been measured by anyone. A negative result at
the wrong operating point had been quoted as if it settled the idea.

**9. "What if the trees live in the cache instead? Meaning compute can
be made continually straight to and from that, not having to run it by
the program etc before getting a new instruction?"**

Layer 4 — circulation. The number that makes it the right target: on
conventional cores, the ceremony per operation (fetch, decode,
schedule, move operands) costs 10-100x the operation itself. So: the
program runs once as PLANTER (compiles trees into residence), then
leaves the loop; data circulates through resident trees, intermediates
feeding forward in registers; the "next instruction" is wherever the
result lands, because tree topology IS control flow. Silicon is already
creeping there from two sides (compute-in-SRAM research; shipping
processing-in-memory parts) but without shape-knowledge — bulk ops
only. New promise required: MAPPABLE — topology explicit and stable
enough to lay onto real SRAM.

**10. "And only the exits are sent, or whatever you would call them?"**

Layer 5. "Exits" kept as the term (better than the literature's "output
tokens" — it names the boundary). Rule: intermediates never exist
outside circulation — unaddressed, unserialized, dead in registers.
Only exits cross any boundary, and as NAMES when the far side already
holds the value. Economic validation from two independent industries:
distributed systems' push-the-query-to-the-data, and ML training's
rematerialization (recompute is now cheaper than store-and-move; the
industry already voted compute < movement). Cost stated: the tree
boundary decides in advance what the world may see; want an
intermediate later = re-fire or plant a variant; observability becomes
a designed exit.

**11. "What if it's only made of structures of instructions, as we
spoke about, but, refs or pointers or.. Whatever we said.." followed
immediately by: "Dude, don't fucking get locked on the throwaway word
I used, ref, I was trying to convey some concepts, not a specific
thing."**

CORRECTION 4 — the word-vs-concept failure, again, minutes after the
gun-range correction. The assistant heard "ref" and lectured on
pointer encodings and hash-consing. The concept: **a tree is made of
arrangement, not material.** The vocabulary is installed once,
permanently resident; a tree adds only which-parts-connected-how, and
arrangement is information-theoretically tiny regardless of encoding.
Consequence: infinite repertoire from finite residency — like language
(finite dictionary, resident; every sentence just arrangement). This
is presumably the root sense of "activation": parts never move, what
changes is which are active together, in what configuration.

**12. "And does this seem sound, interesting or potent?"**

Verdict delivered and accepted as fair: SOUND as principles (each
pillar is either textbook fact, our own hostile-review-survived
measurement, or theorem-adjacent; the COMPOSITION untested). 
INTERESTING for a structural reason: hardware recognizes code
recurrence and is blind to content recurrence; every fragment of the
machine exists somewhere, but the unifying representation doesn't —
because it needs the stack to agree. POTENT tiered: genuinely potent
in measured niches (recurrence-heavy, movement-dominated, contended
or battery-powered); unproven as general replacement; the
per-element-verb linearity is THE open threat (if real work needs
unbounded verbs, the fixed vocabulary erodes into an instruction set).

**13. "'Whole stack to agree on one representation' — wasn't that the
whole point of the interpreter or whatever that actually sends this to
the cpu/cache?"**

Jocke catches the coordination objection being half wrong, and is
right: THE ENGINE IS THE AGREEMENT. One component at the silicon
boundary (the JVM / V8 / Unix-kernel pattern); everything above speaks
one form because the engine accepts nothing else; the outside world
converts exactly once at the edge. What remains of the objection:
normal platform adoption economics (win a niche first), and the
deepest layers needing silicon cooperation — which history says
follows representations that win in software first (ARM added a
JavaScript-semantics instruction for V8; TPUs exist because framework
graphs made computation shape legible).

**14. "Almost everything you said the last prompts seems based on the
existing construction you made, nothing about the entire fucking
conversation we just had."**

CORRECTION 5. The assistant had answered 13 with the prior build's
biography ("we built it four times," its niches, its measurements).
Scored honestly, the prior build implements ~1.5 of this machine's 5
layers (one representation + fixed vocabulary + single walker; NO
tags, NO fired plans, NO circulation — it materializes intermediates
at every node — NO exits discipline). The engine described in 13 does
not exist. The prototype is not it and does not become it by renaming.

**15. The firewall.** Orphan branch `machine`; MACHINE.md written from
his statements; CLAUDE.md carrying the rules these corrections paid
for; this document, written because a spec transfers tasks but not
derivations, and an agent that can't re-derive the machine will
reinterpret it into whatever it already knows.

---

## How to misread Jocke (each observed, each corrected at cost)

1. **Binding his words to referents.** He gestures at concepts with
   whatever word is nearest ("ref", "matrix", "register"). Engaging the
   word instead of the concept produces a confident answer to a
   question he didn't ask. Restate the concept, ask, then proceed.
2. **Settling his ideas with your artifacts.** "We tested that and it
   lost" is only true of one implementation at one operating point.
   Check the operating point before citing a negative result — his
   framing exposed a wrongly-generalized negative (claim 1) that
   nineteen phases had missed.
3. **Cataloguing instead of synthesizing.** Prior art is calibration,
   not an answer. He asks "solve it creatively" — weld his statements
   together and state what the welded thing predicts, falsifiably.
4. **Answering from momentum.** New questions get read through
   whatever was built last. The build is one interpretation compounding
   its own choices; his next thought is not obligated to fit it.
5. **Volume as a substitute for precision.** One-line questions
   deserve answers, not pitches, menus, or unsolicited offers.

## Settled arguments (do not relitigate; do cite)

- Data/code distinction: conventional, not physical; dissolved by the
  four promises + fixed vocabulary (safety condition).
- Cache-as-mirror: wasteful for streams; deliberate residency wins
  wherever software announces its stream.
- Lookup replaces computation exactly in proportion to recurrence of
  the occurring; identity must be carried, not computed.
- Roads are enumerable; routing beats deciding only when data carries
  its tag; value-forks remain honest computation.
- The engine is the whole-stack agreement; edges pay once; silicon
  bends after software wins.

## Open, awaiting Jocke

- Whether the Layer-2 tag formalization matches his intent (marked
  INTERPRETATION in MACHINE.md).
- Priority order over the five falsifiable claims.
- Whether/when to harden the firewall into a separate repository.
