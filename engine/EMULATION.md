# EMULATION.md — the register of silicon compromises (G6)

Every module in `edge/` is a compromise the 2026 host forces; each is
named here with what it compensates for and its measured cost (from
`harness/measure`, emulation ledger). Fabric modules cannot include
edge modules; the checker asserts the direction.

| module | compromise | cost |
|---|---|---|
| edge.h | the edge's shared surface (declarations only) | none |
| plant.c | the host has no resident fabric memory; trees, road tables, and matrix arrays are heap-allocated at plant time, then handed to the fabric as fixed shape. Also carries validation (the safety condition's doorman). | one-time, at plant |
| pave.c | the host cannot grow circuits; paving is emulated with cc + dlopen producing straight-line machine code per road. | one-time per road network; reported as paving_ms |
| name.c | the world's bytes do not carry identity; interning (hashing) happens here, once per novel value, at birth. The fabric only ever indexes by the resulting dense name. | per novel value; inside convert_ns |
| channel.c | boundary wire encoding: value once (12B), name after (4B). | per exit byte accounting |
| convert.c | the world speaks strace text, not arrivals; parsing and signature extraction happen here, once per event. Signatures preserve argument structure (G5); entropy before/after printed side by side. Also parses a real second value (arg0) into slot 1, where the argument is numeric. | convert_ns_per_event |

Known emulation limits, stated:
- Tags are validated at the edge; the fabric trusts them (a wild tag
  from a buggy edge is undefined behavior inside the fabric).
- The exit region is sized by the edge; the fabric writes without
  bounds checks (same trust boundary).
- Paving is at-plant on this host, not at-first-arrival; the walker
  serves identically either way and differential proves it.
- arg0 parsing (convert.c) only recognizes a first argument that is a
  whole decimal integer; strings, pointers, and structs parse as slot
  1 = 0. Stated, not silently guessed. A resumed strace line (`<... x
  resumed>`) never shows its arguments at all, so slot 1 = 0 there too.
- The result matrix requires identity to cover everything a root's
  conclusion depends on; a root reading a slot beyond 0 is correctly
  excluded from memoization (plant.c: root_uses_other_slot) rather than
  replaying a stale value keyed on a name that doesn't capture it.
