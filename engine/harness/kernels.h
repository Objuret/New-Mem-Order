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

static void kernel_wired(nmo_tree *t, uint32_t tag, uint32_t salt,
                         uint32_t exit_to) {
    memset(t, 0, sizeof(*t));
    t->tag = tag;
    krs = 0xC1A140 ^ salt;
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
    t->exit_to[0] = exit_to;
}

static void kernel(nmo_tree *t, uint32_t tag) {
    kernel_wired(t, tag, tag, NMO_EXIT_BOUNDARY);
}

/* fan-out: same body, two conclusions - the final SELECT and the
 * pre-fork mix - each wired to its own target */
static void kernel_fan2(nmo_tree *t, uint32_t tag, uint32_t salt,
                        uint32_t to0, uint32_t to1) {
    kernel_wired(t, tag, salt, to0);
    t->nexits = 2;
    t->exits[1] = (uint16_t)(t->nnodes - 4);    /* the norm-path mix */
    t->exit_to[1] = to1;
}

/* richer-than-u64 payload: a genuine two-slot kernel. Slot 0 carries
 * the event's primary value (e.g. a syscall's return value, as every
 * other kernel here uses); slot 1 carries a second, independent value
 * (e.g. its first argument). The short-transfer fork below - "did
 * fewer units come back than were asked for" - needs BOTH alive at
 * once and cannot be expressed at all from a single carried u64; it
 * is the concrete capability this vocabulary extension adds. */
static void kernel_rich_wired(nmo_tree *t, uint32_t tag, uint32_t salt,
                              uint32_t exit_to) {
    memset(t, 0, sizeof(*t));
    t->tag = tag;
    krs = 0xC1A140 ^ salt;
    uint16_t n = 0;
    t->nodes[n].op = NMO_OP_INPUT; t->nodes[n].slot = 0; n++;  /* 0 */
    t->nodes[n].op = NMO_OP_INPUT; t->nodes[n].slot = 1; n++;  /* 1 */
#define K(o, A, B, IMM) do { t->nodes[n].op = (o); t->nodes[n].a = (A); \
    t->nodes[n].b = (B); t->nodes[n].imm = (IMM); n++; } while (0)
    K(NMO_OP_CONST, 0, 0, 0xFFFFFFFFFFFFF000ULL);   /* 2 */
    K(NMO_OP_LT, 2, 0, 0);          /* 3: errno fork (slot 0 alone)     */
    K(NMO_OP_LT, 0, 1, 0);          /* 4: short-transfer fork - needs
                                        slot 0 AND slot 1 alive at once,
                                        unbuildable from one carried u64*/
    K(NMO_OP_CONST, 0, 0, krnd() | 1);              /* 5 */
    K(NMO_OP_MUL, 0, 5, 0);         /* 6: mix on slot 0                 */
    K(NMO_OP_XOR, 6, 1, 0);         /* 7: fold in slot 1                */
    K(NMO_OP_CONST, 0, 0, krnd() % 62 + 1);         /* 8 */
    K(NMO_OP_ROTL, 7, 8, 0);        /* 9: normal-path result            */
    K(NMO_OP_CONST, 0, 0, krnd());                  /* 10 */
    K(NMO_OP_ADD, 9, 10, 0);        /* 11: shortfall-path result        */
    t->nodes[n].op = NMO_OP_SELECT;
    t->nodes[n].a = 4; t->nodes[n].b = 11; t->nodes[n].c = 9;
    n++;                            /* 12: short ? shortfall : normal   */
    K(NMO_OP_CONST, 0, 0, krnd() | (tag + 1));      /* 13 */
    K(NMO_OP_XOR, 0, 13, 0);        /* 14: error-path value             */
    t->nodes[n].op = NMO_OP_SELECT;
    t->nodes[n].a = 3; t->nodes[n].b = 14; t->nodes[n].c = 12;
    n++;                            /* 15: errno ? err : midsel         */
#undef K
    t->nnodes = n;
    t->nexits = 1;
    t->exits[0] = n - 1;
    t->exit_to[0] = exit_to;
}

static void kernel_rich(nmo_tree *t, uint32_t tag) {
    kernel_rich_wired(t, tag, tag, NMO_EXIT_BOUNDARY);
}
#endif
