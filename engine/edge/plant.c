#include "edge.h"
#include <stdlib.h>
#include <string.h>

static int op_arity(uint8_t op) {
    switch (op) {
    case NMO_OP_INPUT: case NMO_OP_CONST: return 0;
    case NMO_OP_SELECT: return 3;
    default: return op < NMO_OP_COUNT ? 2 : -1;
    }
}

int nmo_tree_valid(const nmo_tree *t, uint32_t ntags) {
    if (t->nnodes == 0 || t->nnodes > NMO_MAX_NODES) return -1;
    if (t->nexits == 0 || t->nexits > NMO_MAX_EXITS) return -2;
    if (t->tag >= ntags) return -3;
    for (uint16_t i = 0; i < t->nnodes; i++) {
        int ar = op_arity(t->nodes[i].op);
        if (ar < 0) return -4;
        if (ar >= 1 && t->nodes[i].a >= i) return -5;
        if (ar >= 2 && t->nodes[i].b >= i) return -5;
        if (ar >= 3 && t->nodes[i].c >= i) return -5;
    }
    for (uint16_t p = 0; p < t->nexits; p++) {
        if (t->exits[p] >= t->nnodes) return -6;
        uint32_t to = t->exit_to[p];
        if (to != NMO_EXIT_BOUNDARY && to >= ntags) return -7;
    }
    return 0;
}

nmo_fabric *nmo_plant(const nmo_tree *trees, uint32_t ntrees,
                      uint32_t ntags, uint32_t name_span,
                      uint64_t *exit_region) {
    for (uint32_t i = 0; i < ntrees; i++)
        if (nmo_tree_valid(&trees[i], ntags) != 0) return 0;

    nmo_fabric *f = calloc(1, sizeof(*f));
    f->roads = calloc(ntags, sizeof(nmo_road));
    f->ntags = ntags;
    f->name_span = name_span;
    f->exit_at = exit_region;
    if (name_span) {
        f->matrix = malloc((size_t)ntags * name_span * 8);
        f->matrix_known = calloc((size_t)ntags * name_span, 1);
        f->matrix_ok = calloc(ntags, 1);
    }

    nmo_tree *copy = calloc(ntrees, sizeof(nmo_tree));
    memcpy(copy, trees, ntrees * sizeof(nmo_tree));
    for (uint32_t i = 0; i < ntrees; i++) {
        uint32_t tag = copy[i].tag;
        f->roads[tag].fn = nmo_walk_road;   /* slow road until paved */
        f->roads[tag].tree = &copy[i];
        /* result matrix only where identity arrives: single-boundary-
         * exit entry roads */
        if (name_span && copy[i].nexits == 1
            && copy[i].exit_to[0] == NMO_EXIT_BOUNDARY)
            f->matrix_ok[tag] = 1;
    }
    return f;
}

void nmo_unplant(nmo_fabric *f) {
    if (!f) return;
    /* tree copies: all roads share one block (first planted tree) */
    const nmo_tree *base = 0;
    for (uint32_t t = 0; t < f->ntags; t++)
        if (f->roads[t].tree && (!base || f->roads[t].tree < base))
            base = f->roads[t].tree;
    free((void *)base);
    free(f->matrix); free(f->matrix_known); free(f->matrix_ok);
    free(f->roads); free(f);
}
