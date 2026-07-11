/* Claim 3 - exits-only collapses traffic.
 *
 * The same depth-D computation, two boundary disciplines, both sides
 * COUNTED BY CODE (no narrated bytes):
 *
 *   staged      - the conventional pipeline: each of the D operation
 *                 stages materializes its full output array and that
 *                 array crosses the boundary to the next stage.
 *                 Bytes counted as they are written.
 *   exits-only  - the engine: the tree fires in circulation,
 *                 intermediates die inside, only the exit crosses -
 *                 through a naming channel, so a value crosses once
 *                 and recurrence crosses as a 4-byte reference.
 *
 * Predicted sign (MACHINE.md): ratio ~ intermediates over exits.
 * Streams: unique-heavy (worst case for naming) and recurrent
 * (where names collapse traffic further).
 * Parity: the staged pipeline's final values must equal the engine's
 * decoded channel output, element for element.
 */
#define _GNU_SOURCE
#include "../../engine/nmo.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t rs = 0x00C1A1400DBA5E5ULL;
static uint64_t rnd(void) {
    rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27;
    return rs * 0x2545F4914F6CDD1DULL;
}

static void make_chain(nmo_arrangement *a, int depth, uint64_t *consts,
                       uint8_t *ops) {
    memset(a, 0, sizeof(*a));
    a->nodes[0].op = NMO_OP_INPUT;
    uint16_t n = 1, prev = 0;
    static const uint8_t mix[4] = { NMO_OP_ADD, NMO_OP_XOR,
                                    NMO_OP_MUL, NMO_OP_ROTL };
    for (int d = 0; d < depth; d++) {
        uint8_t op = mix[d % 4];
        uint64_t c = (op == NMO_OP_ROTL) ? (rnd() % 63) + 1
                     : (op == NMO_OP_MUL) ? (rnd() | 1) : rnd();
        consts[d] = c; ops[d] = op;
        a->nodes[n].op = NMO_OP_CONST;
        a->nodes[n].imm = c;
        n++;
        a->nodes[n].op = op;
        a->nodes[n].a = prev;
        a->nodes[n].b = (uint16_t)(n - 1);
        prev = n++;
    }
    a->nnodes = n; a->nexits = 1; a->exits[0] = prev;
}

static uint64_t apply(uint8_t op, uint64_t l, uint64_t r) {
    switch (op) {
    case NMO_OP_ADD: return l + r;
    case NMO_OP_XOR: return l ^ r;
    case NMO_OP_MUL: return l * r;
    case NMO_OP_ROTL:
        return (l << (r & 63)) | (l >> ((64 - (r & 63)) & 63));
    default: return 0;
    }
}

/* exits land here in order (single tag, no memo -> arrival order) */
static uint64_t *exit_vals;
static size_t exit_n;
static void sink(void *ctx, const nmo_exit *ex, size_t n) {
    (void)ctx;
    for (size_t i = 0; i < n; i++) exit_vals[exit_n++] = ex[i].val;
}

int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: %s <depth> <M> <unique|recurrent>\n",
                argv[0]);
        return 1;
    }
    int depth = atoi(argv[1]);
    uint32_t M = (uint32_t)strtoul(argv[2], 0, 10);
    int recurrent = strcmp(argv[3], "recurrent") == 0;

    uint64_t consts[256]; uint8_t ops[256];
    nmo_arrangement arr;
    rs = 0x00C1A1400DBA5E5ULL ^ (uint64_t)depth;
    make_chain(&arr, depth, consts, ops);
    arr.tag = 0;

    nmo_record *recs = malloc((size_t)M * sizeof(*recs));
    for (uint32_t i = 0; i < M; i++) {
        recs[i].tag = 0; recs[i].pad = 0;
        recs[i].val = recurrent ? rnd() % 1000 : rnd();
    }

    /* ---- staged pipeline: every stage's output crosses ---- */
    uint64_t *cur = malloc((size_t)M * 8), *nxt = malloc((size_t)M * 8);
    uint64_t staged_bytes = 0;
    for (uint32_t i = 0; i < M; i++) cur[i] = recs[i].val;
    for (int d = 0; d < depth; d++) {
        for (uint32_t i = 0; i < M; i++)
            nxt[i] = apply(ops[d], cur[i], consts[d]);
        staged_bytes += (uint64_t)M * 8;    /* this array crossed */
        uint64_t *t = cur; cur = nxt; nxt = t;
    }

    /* ---- engine: circulation inside, exits-only outside ---- */
    exit_vals = malloc((size_t)M * 8);
    exit_n = 0;
    nmo_config cfg = { .max_tags = 1, .batch = 256, .memo_entries = 0,
                       .sink = sink };
    nmo_engine *e = nmo_create(&cfg);
    if (!e || nmo_plant(e, &arr) != 0) return 2;
    nmo_feed(e, recs, M);
    nmo_drain(e);
    if (exit_n != M) { fprintf(stderr, "exit count\n"); return 3; }

    /* parity: staged result == engine exits, element for element */
    if (memcmp(cur, exit_vals, (size_t)M * 8) != 0) {
        fprintf(stderr, "PARITY VIOLATION\n");
        return 3;
    }

    /* the boundary crossing, named */
    nmo_channel *ch = nmo_chan_create(e);
    nmo_chan_send(ch, exit_vals, M);
    uint64_t exit_bytes = nmo_chan_bytes_sent(ch);

    /* decode side must reconstruct exactly */
    uint64_t *back = malloc((size_t)M * 8);
    size_t dn = nmo_chan_decode(ch, back, M);
    if (dn != M || memcmp(back, exit_vals, (size_t)M * 8) != 0) {
        fprintf(stderr, "DECODE PARITY VIOLATION\n");
        return 3;
    }

    printf("{\"depth\":%d,\"dist\":\"%s\",\"M\":%u,"
           "\"staged_bytes\":%llu,\"exit_bytes\":%llu,"
           "\"ratio\":%.3f,\"intermediates\":%d}\n",
           depth, argv[3], M,
           (unsigned long long)staged_bytes,
           (unsigned long long)exit_bytes,
           (double)staged_bytes / (double)exit_bytes, depth);

    nmo_chan_destroy(ch);
    nmo_destroy(e);
    free(recs); free(cur); free(nxt); free(exit_vals); free(back);
    return 0;
}
