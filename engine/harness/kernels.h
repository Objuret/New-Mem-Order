/* per-tag enrichment kernel, one definition for every harness */
#ifndef NMO_KERNELS_H
#define NMO_KERNELS_H
#include "../fabric/fabric.h"
#include <string.h>

static uint64_t krs;
static uint64_t krnd(void) {
    krs ^= krs >> 12; krs ^= krs << 25; krs ^= krs >> 27;
    return krs * 0x2545F4914F6CDD1DULL;
}

static void kernel(nmo_tree *t, uint32_t tag) {
    memset(t, 0, sizeof(*t));
    t->tag = tag;
    krs = 0xC1A140 ^ tag;
    uint16_t n = 0;
    t->nodes[n++].op = NMO_OP_INPUT;
#define K(o, A, B, IMM) do { t->nodes[n].op = (o); t->nodes[n].a = (A); \
    t->nodes[n].b = (B); t->nodes[n].imm = (IMM); n++; } while (0)
    K(NMO_OP_CONST, 0, 0, 0xFFFFFFFFFFFFF000ULL);
    K(NMO_OP_LT, 1, 0, 0);
    K(NMO_OP_CONST, 0, 0, krnd() % 9 + 3);
    K(NMO_OP_SHR, 0, 3, 0);
    K(NMO_OP_CONST, 0, 0, krnd() | 1);
    K(NMO_OP_MUL, 0, 5, 0);
    int reps = (int)(krnd() % 3) + 1;
    uint16_t m = 6;
    for (int i = 0; i < reps; i++) {
        K(NMO_OP_CONST, 0, 0, krnd());
        K(NMO_OP_XOR, m, n - 1, 0);
        K(NMO_OP_CONST, 0, 0, krnd() % 62 + 1);
        K(NMO_OP_ROTL, n - 2, n - 1, 0);
        m = n - 1;
    }
    K(NMO_OP_ADD, m, 4, 0);
    uint16_t norm = n - 1;
    K(NMO_OP_CONST, 0, 0, krnd() | (tag + 1));
    K(NMO_OP_XOR, 0, n - 1, 0);
    uint16_t err = n - 1;
    t->nodes[n].op = NMO_OP_SELECT;
    t->nodes[n].a = 2; t->nodes[n].b = err; t->nodes[n].c = norm;
    n++;
#undef K
    t->nnodes = n;
    t->nexits = 1;
    t->exits[0] = n - 1;
    t->exit_to[0] = NMO_EXIT_BOUNDARY;
}
#endif
