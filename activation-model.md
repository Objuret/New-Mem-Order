# The Activation Model

Authoritative specification. Code conforms to this document; this document changes only by explicit acceptance from Jocke. Amendments proposed elsewhere have no force until merged here.

---

## 0. Purpose

Computers spend most of their effort moving and converting bytes rather than computing on them: parse, serialize, compress, decompress, copy, reformat — the same information shuttled between a stored form, a wire form, and an executable form, with machinery and bugs at every conversion. Moving a byte costs orders of magnitude more than computing on it; memory and bandwidth, not compute, are the bottleneck. This model tests whether the entire conversion-and-movement category can be deleted. The goals, in one place:

- **Everything stays small and runs as-is.** Data is never decompressed to be used. Its compact form IS its runnable form: a stored file is an instruction not yet fired, and reading is running. No decompress-before-run exists anywhere.
- **The compactness comes from universality.** One fixed set of structures is shared by ALL data and ALL programs — not per-app schemas, not negotiated formats. Because both sides already hold the structures, anything sent or stored carries only what the receiver doesn't already have: structure references + values. Reuse across everything is the source of the compression, not a codec.
- **Universality buys residency.** Because the structure set is small and shared by everything, it lives permanently in the fastest available place — always resident, always warm, never fetched, never evicted. Traffic consists of references into machinery that is already there.
- **Transfer is activation, not delivery.** A message doesn't deliver a payload to be parsed; it names which resident structures to fire with which values. Receiving IS executing. Nothing is ever "in a format," because a format is only needed when the receiver is empty — and the receiver is never empty.
- **Garbage is unexpressible.** Nothing can be sent or stored except references to structures with values. Malformed input isn't detected and rejected — it cannot be constructed. The parsing-bug class, historically the largest vulnerability class in software, has nothing to exist for.
- **Nothing is written, so simultaneity is free.** Values exist only in flight; firings can't clobber anything; the coordination machinery of the mutation world (locks, races, stores) has nothing to exist for.
- **Nothing exists unless demanded.** Nothing fires uncommanded; an instruction never demanded simply stays unsent, wherever it already is, costing nothing. Storage therefore needs no system: no database, no index, no store component — persistence is unsent instructions sitting in files, found by held references.

Every rule below exists to protect these properties. When a judgment call arises that the rules don't cover, decide in their favor — above all: never let a second representation of anything come into existence.

---

## 1. Axioms

**A1 — Fixed structures.** There exists one fixed, universal set of structures. They are permanently resident and immutable. Nothing can create, modify, or delete a structure at runtime. They are the only machinery. *(Contents of the set: OPEN. Determining the actual set is the prototype's job.)*

**A2 — Values only in flight.** No data layer exists. There is no store, no state, no objects, no mutation. The only things that move are instructions. An instruction = which structures + which values. Values exist only inside instructions.

**A3 — Receive = execute.** A message is not a payload to be parsed. It is a firing pattern: which resident structures to wake, with which operands, wired to which other structures. Arrival is the event. There is no "at rest, waiting to be read" state for a message.

**A4 — Demand-driven, all the way down.** Nothing fires unless commanded. An instruction that is never demanded simply stays unsent, wherever it already is (a file, a sender, a definition). No component parks, manages, or indexes unsent instructions. Whoever will demand an instruction holds its reference — a name, nothing more.

---

## 2. Definitions

- **Structure**: an immutable, resident, executable unit from the universal set. Referenced by ID.
- **Instruction**: structure ID(s) + values + wiring. A composition tree of any depth — series of operations, series of series, arbitrarily nested. It fires whole: the entire tree. Simultaneously the wire format, the stored format, and the executable form. There is no other representation of anything.
- **Grammar nodes**: the instruction format itself has exactly these node types — literal value, structure composition, demand, error. Grammar nodes are part of the model core, not the library; adding one is a spec amendment.
- **Demand node**: fires the unsent instruction named by a held, literal reference (never a computed one — A4: a name, nothing more). A demand node marks its enclosing instruction as world-dependent.
- **Error**: a reserved grammar node. A firing returns a value or an error, distinguishable by construction — never by content convention. A refusal at any depth aborts the whole indivisible firing and propagates to the demander.
- **Value**: operand content inside an instruction. No size limit — a huge value is just a mostly-literal instruction (a file is already one). Anything that varies (clock readings, randomness) enters as a value; structures never conjure it.
- **Output**: returns to the demander. The demand is the return path — same as a function return today. No naming, no parking, no lookup.
- **Terminal structure**: a structure whose firing hands off to the world (emit-to-screen, emit-to-wire, emit-to-disk). This is the model's edge; A2 applies up to it, not past it. Terminals touching shared world-state bind to exactly one router; their atomicity comes from fires-whole.
- **Firing**: resolving the structure IDs and running them with the given values, whole and indivisible. Deterministic below demand boundaries: same structure + same values = same result, always. Across a demand boundary, the world may have changed — determinism and cacheability apply below demand nodes, not across them. Variety comes from combinations, cascades, and demands.
- **Router**: the component that receives instructions and dispatches them to structures. For pure firings, count and placement are pure engineering — nothing coordinates. The single qualifier: terminals sharing world-state must share a router (see Terminal structure).
- **Reference**: the name a demander holds for an unsent instruction. Equivalent role to a file path today.

---

## 3. Execution model

1. Something demands an instruction (by reference) or sends one directly.
2. The instruction arrives at a router.
3. Router resolves structure IDs to resident structures.
4. The instruction fires, whole — the entire composition tree, however deep. Simultaneous pure firings fire simultaneously — unlimited, zero coordination; nothing is written, so there is no cell two firings could clobber. The sole coordination point in the system is at terminals sharing world-state (see §2, Terminal structure).
5. The output returns to the demander, or — via a terminal structure — exits to the world. An output can itself be an instruction, demanded onward or left unsent.

There is no step where bytes are parsed, converted, decompressed as a separate phase, or interpreted against a format. Decompression/interpretation IS the firing.

---

## 4. What the axioms delete (and why)

| Deleted | Deleted by | Reason |
|---|---|---|
| Parsing / formats | A3 | A format is what you need when the receiver is empty. The receiver is never empty; the message only selects resident capability. Malformed input is unexpressible, not rejected. |
| Serialization / deserialization | A2 | There is no second representation to convert to or from. The instruction is the only form. |
| Decompress-before-run | A3 | The compressed form is the firing pattern. Reading is running. |
| Write races / locks | A2 | Nothing is written. Simultaneous firings on the same values produce independent onward instructions; there is no cell to clobber. |
| Store management (GC, defrag, currency tracking) | A2 + A4 | No store exists. Unsent instructions sit where they already are and cost nothing. Deleting an unsent instruction = deleting a file, same as now. |
| Global coordination / queues / organizers | A4 | Demand-driven firing needs no background machinery. The hardware already works this way (nothing polls memory; every request is commanded). The model inherits this. |
| Dictionary/version negotiation | A1 | The structure set is frozen. All parties agree by construction. Nothing can drift because nothing is mutable. |
| Cache invalidation / recomputation | Determinism | Below demand boundaries, same instruction = same result, forever: a result is cacheable by instruction identity and replay is trivial. Across a demand boundary the world may have changed; only there can a re-demand differ. |

---

## 5. Correspondence with existing hardware behavior

Stated to confirm the model matches how machines already operate, not to derive the model from them:

- Every memory operation today is commanded by an instruction upstream; the memory controller never initiates. → A4 is already physical reality.
- A compressed file on disk already IS an unsent instruction: it sits, unexecuted, costing nothing, until demanded. → A4's storage story requires no new component. Storage = the disk, holding unsent instructions, found by reference (path).
- An LZ stream is already a program and its decompressor its interpreter. → A3 makes this the universal case instead of a special case.

---

## 6. The load-bearing empirical claim

Everything above is derivable from the axioms except one thing, which is measurable:

**Claim: real work reduces to a small, stable set of structure-compositions fired with high repetition.**

- If a small structure set covers real workloads → instructions stay near the information-theoretic floor (carrying only what the receiver doesn't already have), residency pays, the model stands.
- If not → values-in-flight balloon into carrying all complexity (bytes rebuilt, in flight) or the structure set balloons (software rebuilt, resident).

Falsification test: take a real workload, express its operations as compositions over the library, count distinct compositions vs. total fired work. The count must report grammar nodes alongside library structures — relocating capability from library to grammar does not shrink the true number. Encouraging prior: ~300 syscalls mediate all program↔OS interaction, stable for decades.

---

## 7. Boundaries (honest edges, not flaws)

- **Entropy-dense content** (media, encrypted data, novel bytes): rides as huge literal values. No size limit on values — a file is already an instruction. The model degrades gracefully; compression comes from structure references replacing repeated content, never from size caps.
- **References must be held.** A demander must know the name of what it demands. This is a reference, not a database — same burden as knowing a file path today.
- **Determinism's price**: anything that varies (time, randomness, sensor input) must enter as a value in an instruction, never be conjured inside a structure. This is a discipline the runtime must enforce, not a free property.
- **Security** (unforgeable structure naming, firing permissions): explicitly deferred. Noted only that A1 removes structure-modification attacks by construction.

---

## 8. Software realization (no new hardware)

- **Structures**: fixed library, compiled native, mmap'd read-only. Immutability enforced by page permissions. Contents discovered by the prototype (per A1's open item).
- **Router**: event loop. Resolve IDs → dispatch. Small. Start with one; add more freely — nothing coordinates.
- **Instructions**: compact binary — structure IDs + values + wiring, nested. File format = wire format = execution format.
- **Terminals**: thin wrappers over syscalls (write to fd, socket send, framebuffer). The model's edge, explicit.
- **Storage**: none built. Unsent instructions are files. Demanding one = reading the file = firing it.

First prototype answers claim §6 directly: build one real small workload on it and count how many structures (and grammar nodes) were actually needed.
