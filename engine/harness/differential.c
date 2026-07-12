/* Walker and paved roads must be bit-identical, in arrival order,
 * matrix on and off, including road-to-road circulation. */
#include "../edge/edge.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t rs = 0xDEADBEEF01234567ULL;
static uint64_t rnd(void) {
    rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27;
    return rs * 0x2545F4914F6CDD1DULL;
}

static int failures;
#define CHECK(c, msg) do { if (!(c)) { failures++; \
    fprintf(stderr, "FAIL %d: %s\n", __LINE__, msg); } } while (0)

static void gen_tree(nmo_tree *t, uint32_t tag, uint32_t exit_to) {
    memset(t, 0, sizeof(*t));
    t->tag = tag;
    t->nnodes = (uint16_t)(4 + rnd() % 60);
    t->nodes[0].op = NMO_OP_INPUT;               /* slot 0 (default) */
    t->nodes[1].op = NMO_OP_INPUT;
    t->nodes[1].slot = 1;                        /* every tree also
                                                     addresses slot 1,
                                                     so multi-slot
                                                     dispatch is on the
                                                     differential path,
                                                     not a side case */
    for (uint16_t i = 2; i < t->nnodes; i++) {
        uint32_t roll = (uint32_t)(rnd() % 100);
        nmo_node *nd = &t->nodes[i];
        if (roll < 15) { nd->op = NMO_OP_CONST; nd->imm = rnd(); }
        else if (roll < 25 && i >= 3) {
            nd->op = NMO_OP_SELECT;
            nd->a = rnd() % i; nd->b = rnd() % i; nd->c = rnd() % i;
        } else {
            nd->op = (uint8_t)(NMO_OP_SELECT + 1 +
                     rnd() % (NMO_OP_COUNT - NMO_OP_SELECT - 1));
            nd->a = rnd() % i; nd->b = rnd() % i;
        }
    }
    t->nexits = 1;
    t->exits[0] = t->nnodes - 1;
    t->exit_to[0] = exit_to;
}

int main(void) {
    const uint32_t NT = 24, M = 50000;
    nmo_tree trees[24];
    /* tags 0..19 boundary; 20..23 fan out: one exit feeds a boundary
     * tree (circulation), a second exits the boundary directly */
    for (uint32_t t = 0; t < 20; t++) gen_tree(&trees[t], t, NMO_EXIT_BOUNDARY);
    for (uint32_t t = 20; t < NT; t++) {
        gen_tree(&trees[t], t, t - 20);
        trees[t].nexits = 2;
        trees[t].exits[1] = (uint16_t)(trees[t].nnodes / 2);
        trees[t].exit_to[1] = NMO_EXIT_BOUNDARY;
    }

    nmo_arrival *arr = malloc(M * sizeof(*arr));
    nmo_namer *nm = nmo_namer_new();
    for (uint32_t i = 0; i < M; i++) {
        arr[i].tag = (uint32_t)(rnd() % NT);
        arr[i].val[0] = rnd() % 4096;    /* recurrence-heavy */
        arr[i].val[1] = rnd() % 4096;    /* slot 1, independent stream */
        arr[i].name = nmo_name(nm, arr[i].val[0], 0);
    }
    uint32_t span = nmo_name_count(nm);

    uint64_t *ex[4];
    for (int k = 0; k < 4; k++) ex[k] = calloc((size_t)M * 2 + 8, 8);
    size_t nex[4];

    for (int k = 0; k < 4; k++) {       /* walker/paved x matrix off/on */
        int paved = k & 1, matrix = k & 2;
        nmo_fabric *f = nmo_plant(trees, NT, NT, matrix ? span : 0, ex[k]);
        CHECK(f, "plant");
        if (paved)
            CHECK(nmo_pave_all(f, getenv("NMO_JIT_DIR"), 0) == 0, "pave");
        for (uint32_t i = 0; i < M; i++)
            nmo_arrive_inl(f, arr[i].tag, arr[i].name, arr[i].val);
        nex[k] = (size_t)(f->exit_at - ex[k]);
        nmo_unplant(f);
    }
    for (int k = 1; k < 4; k++) {
        CHECK(nex[k] == nex[0], "exit count differs");
        CHECK(!memcmp(ex[k], ex[0], nex[0] * 8),
              "exit stream differs (order or value)");
    }
    CHECK(nex[0] > M, "fan-out must add exits");

    /* invalid trees rejected at the door */
    nmo_tree bad;
    gen_tree(&bad, 0, NMO_EXIT_BOUNDARY);
    bad.nodes[2].op = NMO_OP_COUNT;
    CHECK(nmo_tree_valid(&bad, NT) != 0, "vocabulary violation accepted");
    gen_tree(&bad, 0, 999);
    CHECK(nmo_tree_valid(&bad, NT) != 0, "wild exit target accepted");

    /* channel round-trip */
    nmo_chan *c = nmo_chan_new(nm);
    nmo_chan_send(c, ex[0], nex[0]);
    uint64_t *back = malloc(nex[0] * 8);
    CHECK(nmo_chan_recv(c, back, nex[0]) == nex[0], "chan count");
    CHECK(!memcmp(back, ex[0], nex[0] * 8), "chan round-trip");
    nmo_chan_del(c);

    nmo_namer_del(nm);
    if (failures) { printf("%d FAILURES\n", failures); return 1; }
    printf("differential: walker==paved, matrix on==off, order exact, "
           "%u exits\n", (unsigned)nex[0]);
    return 0;
}
