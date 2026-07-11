/* THE ENGINE - public surface.
 *
 * MACHINE.md: "One component at the silicon boundary IS the whole-stack
 * agreement: it holds the vocabulary and road table hot, receives
 * tagged arrivals, routes into fired plans, hosts circulation, emits
 * only exits, paves unknown shapes through its single slow walker, and
 * converts the outside world's bytes exactly once at the edge."
 *
 * This is that component as an embeddable runtime (OPTIONS.md 2a).
 * Everything a client can do is here: install arrangements (plant),
 * feed tagged records, receive exits, open boundary channels. There is
 * deliberately no way to address an intermediate, no way to execute
 * anything but arrangements of the fixed vocabulary, and no dispatch
 * surface that inspects payloads.
 *
 * The four promises, as this engine enforces them:
 *   immutable          - records and exit values are by-value u64s;
 *                        nothing planted or fed is ever mutated.
 *   identity-carrying  - a value IS its identity (v0: u64 payloads);
 *                        naming interns by carried identity.
 *   recurrence-visible - the result matrix and exit naming turn
 *                        repetition into reference automatically.
 *   mappable           - arrangements are explicit finite DAGs over
 *                        the vocabulary; topology is the artifact.
 *
 * Safety condition: nmo_plant validates every arrangement against the
 * fixed vocabulary (op range, arity, backward-only references,
 * bounded size). Data can only ARRANGE vetted ops; there is no eval.
 */
#ifndef NMO_H
#define NMO_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- the fixed vocabulary (installed once, permanently) ----
 * Binary ops take operands (l, r) from nodes a, b.
 * NMO_OP_INPUT yields the arriving datum's value; NMO_OP_CONST yields
 * the node's immediate; NMO_OP_SELECT is the honest value-fork
 * (layer 2): l ? r : s from nodes a, b, c - a real, small computation,
 * never eliminable, expressed as data dependence. */
#define NMO_BINOPS(X) \
    X(ADD,  l + r) \
    X(SUB,  l - r) \
    X(MUL,  l * r) \
    X(AND,  l & r) \
    X(OR,   l | r) \
    X(XOR,  l ^ r) \
    X(SHL,  l << (r & 63)) \
    X(SHR,  l >> (r & 63)) \
    X(ROTL, (l << (r & 63)) | (l >> ((64 - (r & 63)) & 63))) \
    X(EQ,   (uint64_t)(l == r)) \
    X(LT,   (uint64_t)(l < r)) \
    X(MIN,  l < r ? l : r) \
    X(MAX,  l > r ? l : r)

typedef enum {
    NMO_OP_INPUT = 0,
    NMO_OP_CONST,
    NMO_OP_SELECT,
#define X(NAME, EXPR) NMO_OP_##NAME,
    NMO_BINOPS(X)
#undef X
    NMO_OP_COUNT
} nmo_op;

/* ---- arrangements (a tree is made of arrangement, not material) ---- */
#define NMO_MAX_NODES 256
#define NMO_MAX_EXITS 8

typedef struct {
    uint8_t  op;        /* nmo_op */
    uint16_t a, b, c;   /* operand node indices; must be < own index */
    uint64_t imm;       /* NMO_OP_CONST only */
} nmo_node;

typedef struct {
    uint32_t tag;                       /* direct index into road table */
    uint16_t nnodes;
    uint16_t nexits;
    nmo_node nodes[NMO_MAX_NODES];      /* topological by construction */
    uint16_t exits[NMO_MAX_EXITS];      /* node ids; the tree boundary */
} nmo_arrangement;

/* ---- traffic ---- */
typedef struct {
    uint32_t tag;
    uint32_t pad;
    uint64_t val;
} nmo_record;

typedef struct {
    uint32_t tag;
    uint16_t port;      /* which exit of the arrangement */
    uint16_t pad;
    uint64_t src;       /* global sequence number of the source record */
    uint64_t val;
} nmo_exit;

typedef void (*nmo_exit_sink)(void *ctx, const nmo_exit *exits, size_t n);

/* ---- configuration ---- */
typedef struct {
    uint32_t max_tags;      /* road table size (tags are dense: the edge
                               converts world ids to dense tags, once) */
    uint32_t batch;         /* staging queue depth per road (default 256) */
    uint32_t memo_entries;  /* result-matrix entries per road, power of 2;
                               0 disables the lookup layer */
    int      jit;           /* 1: pave via C compiler into real
                               straight-line machine code (needs cc);
                               0: pave to slotted plans, batch-fired */
    const char *cc;         /* compiler for jit paving (default "cc") */
    const char *jit_dir;    /* scratch dir for jit artifacts */
    nmo_exit_sink sink;
    void    *sink_ctx;
} nmo_config;

typedef struct nmo_engine nmo_engine;

/* ---- accounting (claim discipline: the engine counts itself) ---- */
typedef struct {
    uint64_t fed, routed, unrouted;
    uint64_t memo_hits, memo_misses;
    uint64_t fired_batches, fired_elems;
    uint64_t walker_elems;          /* elements answered by the slow road */
    uint64_t paved_roads, jit_roads;
    uint64_t paving_ns;             /* total cost of all paving, incl. cc */
    uint64_t exits_emitted;
    uint64_t resident_network_bytes;/* arrangements + plans: the road
                                       network itself (claim 4) */
    uint64_t resident_state_bytes;  /* queues + register files + memos */
} nmo_stats;

/* ---- lifecycle ---- */
nmo_engine *nmo_create(const nmo_config *cfg);
void        nmo_destroy(nmo_engine *e);

/* Plant an arrangement (validated; rejects anything outside the fixed
 * vocabulary). Returns 0, or a negative error. Planting installs the
 * tree form only; paving happens on first arrival (arrival = paving). */
int nmo_plant(nmo_engine *e, const nmo_arrangement *a);

/* Feed tagged records. Full batches fire immediately; exits reach the
 * sink. Returns number of records accepted. */
size_t nmo_feed(nmo_engine *e, const nmo_record *recs, size_t n);

/* Fire all partial queues (end of stream / latency bound). */
void nmo_drain(nmo_engine *e);

/* Answer one record through the single slow walker (the generic tree
 * interpreter): one operation at a time, intermediates materialized at
 * every node, control returning to the interpreter loop between steps.
 * This is both the paving path's executor of record and the honest
 * program-mediated baseline for claim 2. Exits written to out[]. */
int nmo_walk(nmo_engine *e, uint32_t tag, uint64_t val, uint64_t *out);

void nmo_get_stats(nmo_engine *e, nmo_stats *s);

/* ---- boundary channels (layer 5: only exits are sent, as names) ----
 * A channel is one boundary crossing. Sending an exit value interns it
 * (first occurrence globally gets a name), then transmits:
 *   far side lacks the name  -> [name u32][value u64]  (12 bytes)
 *   far side holds the name  -> [name u32]             (4 bytes)
 * The receiver reconstructs values exactly; parity is testable. Byte
 * counters are the claim-3 measurement. */
typedef struct nmo_channel nmo_channel;

nmo_channel *nmo_chan_create(nmo_engine *e);
void         nmo_chan_destroy(nmo_channel *c);
size_t       nmo_chan_send(nmo_channel *c, const uint64_t *vals, size_t n);
/* decode from the channel's internal buffer; returns count decoded */
size_t       nmo_chan_decode(nmo_channel *c, uint64_t *vals, size_t cap);
uint64_t     nmo_chan_bytes_sent(const nmo_channel *c);
void         nmo_chan_reset_wire(nmo_channel *c); /* clear buffer+bytes,
                                                     keep far-side state */

#ifdef __cplusplus
}
#endif
#endif
