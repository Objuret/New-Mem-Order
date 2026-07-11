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
| convert.c | the world speaks strace text, not arrivals; parsing and signature extraction happen here, once per event. Signatures preserve argument structure (G5); entropy before/after printed side by side. | convert_ns_per_event |

Known emulation limits, stated:
- Tags are validated at the edge; the fabric trusts them (a wild tag
  from a buggy edge is undefined behavior inside the fabric).
- The exit region is sized by the edge; the fabric writes without
  bounds checks (same trust boundary).
- Paving is at-plant on this host, not at-first-arrival; the walker
  serves identically either way and differential proves it.
