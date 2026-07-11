/* Differential tests: the engine's three execution paths - the slow
 * walker, the slotted firing plan, and the jit-paved machine code -
 * must produce bit-identical exits on randomly generated arrangements
 * and streams. Plus: the safety condition rejects at the door, the
 * result matrix changes nothing observable, channels round-trip
 * exactly, and liveness keeps register files small.
 */
#include "../nmo.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t rs;
static uint64_t rnd(void) {
    rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27;
    return rs * 0x2545F4914F6CDD1DULL;
}

static int failures;
#define CHECK(cond, ...) do { \
    if (!(cond)) { failures++; \
        fprintf(stderr, "FAIL %s:%d: ", __FILE__, __LINE__); \
        fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); } \
    } while (0)

static void gen_arrangement(nmo_arrangement *a, uint32_t tag,
                            uint16_t nnodes, uint16_t nexits) {
    memset(a, 0, sizeof(*a));
    a->tag = tag;
    a->nnodes = nnodes;
    a->nexits = nexits;
    a->nodes[0].op = NMO_OP_INPUT;
    for (uint16_t i = 1; i < nnodes; i++) {
        uint32_t roll = (uint32_t)(rnd() % 100);
        nmo_node *nd = &a->nodes[i];
        if (roll < 15) {
            nd->op = NMO_OP_CONST;
            nd->imm = rnd();
        } else if (roll < 25 && i >= 3) {
            nd->op = NMO_OP_SELECT;
            nd->a = (uint16_t)(rnd() % i);
            nd->b = (uint16_t)(rnd() % i);
            nd->c = (uint16_t)(rnd() % i);
        } else {
            nd->op = (uint8_t)(NMO_OP_SELECT + 1 +
                               rnd() % (NMO_OP_COUNT - NMO_OP_SELECT - 1));
            nd->a = (uint16_t)(rnd() % i);
            nd->b = (uint16_t)(rnd() % i);
        }
    }
    for (uint16_t p = 0; p < nexits; p++)
        a->exits[p] = (uint16_t)(nnodes - 1 - (rnd() % (nnodes / 2 + 1)));
}

/* exit collection: (src, port) -> value */
typedef struct {
    uint64_t *vals;
    uint8_t *seen;
    size_t cap;
    uint16_t nexits;
} collector;

static void sink(void *ctx, const nmo_exit *ex, size_t n) {
    collector *c = ctx;
    for (size_t i = 0; i < n; i++) {
        size_t k = ex[i].src * c->nexits + ex[i].port;
        if (k < c->cap) { c->vals[k] = ex[i].val; c->seen[k] = 1; }
    }
}

static void test_parity(int jit, uint32_t memo_entries, const char *what) {
    const uint32_t NTAGS = 24, M = 60000;
    const uint16_t NEXITS = 3;
    rs = 0xDEADBEEF01234567ULL;

    nmo_arrangement *arrs = malloc(NTAGS * sizeof(*arrs));
    for (uint32_t t = 0; t < NTAGS; t++)
        gen_arrangement(&arrs[t], t, (uint16_t)(4 + rnd() % 60), NEXITS);

    collector col = {
        .vals = calloc((size_t)M * NEXITS, 8),
        .seen = calloc((size_t)M * NEXITS, 1),
        .cap = (size_t)M * NEXITS,
        .nexits = NEXITS,
    };
    nmo_config cfg = {
        .max_tags = NTAGS, .batch = 128, .memo_entries = memo_entries,
        .jit = jit, .jit_dir = getenv("NMO_JIT_DIR"),
        .sink = sink, .sink_ctx = &col,
    };
    nmo_engine *e = nmo_create(&cfg);
    CHECK(e, "engine create (%s)", what);
    for (uint32_t t = 0; t < NTAGS; t++)
        CHECK(nmo_plant(e, &arrs[t]) == 0, "plant %u (%s)", t, what);

    nmo_record *recs = malloc((size_t)M * sizeof(*recs));
    /* recurrence-heavy stream so the memo path actually fires */
    for (uint32_t i = 0; i < M; i++) {
        recs[i].tag = (uint32_t)(rnd() % NTAGS);
        recs[i].val = rnd() % 512;
        recs[i].pad = 0;
    }
    nmo_feed(e, recs, M);
    nmo_drain(e);

    nmo_stats st;
    nmo_get_stats(e, &st);
    CHECK(st.exits_emitted == (uint64_t)M * NEXITS,
          "%s: exits %llu != %llu", what,
          (unsigned long long)st.exits_emitted,
          (unsigned long long)M * NEXITS);
    if (jit)
        CHECK(st.jit_roads == NTAGS, "%s: jit paved %llu/%u roads", what,
              (unsigned long long)st.jit_roads, NTAGS);
    if (memo_entries)
        CHECK(st.memo_hits > 0, "%s: memo never hit", what);

    /* every element, every port, against the walker */
    uint64_t bad = 0;
    for (uint32_t i = 0; i < M; i++) {
        uint64_t out[NMO_MAX_EXITS];
        nmo_walk(e, recs[i].tag, recs[i].val, out);
        for (uint16_t p = 0; p < NEXITS; p++) {
            size_t k = (size_t)i * NEXITS + p;
            if (!col.seen[k] || col.vals[k] != out[p]) bad++;
        }
    }
    CHECK(bad == 0, "%s: %llu exit mismatches vs walker", what,
          (unsigned long long)bad);

    nmo_destroy(e);
    free(arrs); free(recs); free(col.vals); free(col.seen);
    printf("ok: parity (%s)\n", what);
}

static void test_safety(void) {
    nmo_config cfg = { .max_tags = 4, .batch = 32 };
    nmo_engine *e = nmo_create(&cfg);
    nmo_arrangement a;

    memset(&a, 0, sizeof(a));
    a.nnodes = 2; a.nexits = 1; a.exits[0] = 1;
    a.nodes[0].op = NMO_OP_INPUT;
    a.nodes[1].op = NMO_OP_COUNT;               /* not in vocabulary */
    CHECK(nmo_plant(e, &a) < 0, "op outside vocabulary accepted");

    a.nodes[1].op = NMO_OP_ADD; a.nodes[1].a = 1; a.nodes[1].b = 0;
    CHECK(nmo_plant(e, &a) < 0, "self reference accepted");

    a.nodes[1].a = 0; a.nodes[1].b = 5;
    CHECK(nmo_plant(e, &a) < 0, "forward reference accepted");

    a.nodes[1].b = 0; a.exits[0] = 9;
    CHECK(nmo_plant(e, &a) < 0, "exit out of range accepted");

    a.exits[0] = 1; a.nexits = 0;
    CHECK(nmo_plant(e, &a) < 0, "zero exits accepted");

    a.nexits = 1;
    CHECK(nmo_plant(e, &a) == 0, "valid arrangement rejected");
    CHECK(nmo_plant(e, &a) < 0, "re-plant of same tag accepted");

    nmo_destroy(e);
    printf("ok: safety condition rejects at the door\n");
}

static void test_channel(void) {
    nmo_config cfg = { .max_tags = 1, .batch = 32 };
    nmo_engine *e = nmo_create(&cfg);
    nmo_channel *c = nmo_chan_create(e);

    const size_t N = 10000, UNIQ = 100;
    uint64_t *vals = malloc(N * 8);
    rs = 42;
    for (size_t i = 0; i < N; i++) vals[i] = rnd() % UNIQ + 1000000;

    nmo_chan_send(c, vals, N);
    /* every value crosses once; every recurrence is 4 bytes */
    uint64_t expect = UNIQ * 12 + (N - UNIQ) * 4;
    CHECK(nmo_chan_bytes_sent(c) == expect, "wire bytes %llu != %llu",
          (unsigned long long)nmo_chan_bytes_sent(c),
          (unsigned long long)expect);

    uint64_t *got = malloc(N * 8);
    size_t dn = nmo_chan_decode(c, got, N);
    CHECK(dn == N, "decoded %zu != %zu", dn, N);
    CHECK(memcmp(got, vals, N * 8) == 0, "channel round-trip mismatch");

    nmo_chan_destroy(c);
    nmo_destroy(e);
    free(vals); free(got);
    printf("ok: channel (names once, references after, exact decode)\n");
}

static void test_liveness(void) {
    /* a deep op chain must reuse slots: peak live stays tiny no matter
     * the depth - intermediates die (L4) */
    nmo_arrangement a;
    memset(&a, 0, sizeof(a));
    a.tag = 0; a.nnodes = 200; a.nexits = 1; a.exits[0] = 199;
    a.nodes[0].op = NMO_OP_INPUT;
    for (uint16_t i = 1; i < 200; i++) {
        a.nodes[i].op = NMO_OP_ADD;
        a.nodes[i].a = (uint16_t)(i - 1);
        a.nodes[i].b = (uint16_t)(i - 1);
    }
    nmo_config cfg = { .max_tags = 1, .batch = 64 };
    nmo_engine *e = nmo_create(&cfg);
    CHECK(nmo_plant(e, &a) == 0, "chain plant");
    nmo_record r = { .tag = 0, .val = 1 };
    nmo_feed(e, &r, 1);
    nmo_drain(e);
    nmo_stats st;
    nmo_get_stats(e, &st);
    /* register file = nslots * batch * 8; chain needs ~2 slots */
    CHECK(st.resident_state_bytes < 64 * 8 * 8 + cfg.batch * 16,
          "liveness failed: %llu state bytes for a chain",
          (unsigned long long)st.resident_state_bytes);
    nmo_destroy(e);
    printf("ok: liveness (intermediates die, register file stays small)\n");
}

int main(void) {
    test_safety();
    test_channel();
    test_liveness();
    test_parity(0, 0, "plan, no memo");
    test_parity(0, 4096, "plan + result matrix");
    test_parity(1, 0, "jit, no memo");
    test_parity(1, 4096, "jit + result matrix");
    if (failures) { printf("%d FAILURES\n", failures); return 1; }
    printf("all tests passed\n");
    return 0;
}
