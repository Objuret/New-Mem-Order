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

/* boundary exits produced per firing of tag's chain; -1 on cycle.
 * Acyclic wiring + fixed vocabulary = guaranteed termination: a cycle
 * is rejected at the door, not discovered at runtime. */
static int chain_exits(const nmo_tree *const *by_tag, uint32_t tag,
                       uint8_t *state) {
    if (state[tag] == 1) return -1;             /* cycle */
    if (!by_tag[tag]) return -1;                /* dangling target */
    state[tag] = 1;
    int total = 0;
    const nmo_tree *t = by_tag[tag];
    for (uint16_t p = 0; p < t->nexits; p++) {
        if (t->exit_to[p] == NMO_EXIT_BOUNDARY) total++;
        else {
            int sub = chain_exits(by_tag, t->exit_to[p], state);
            if (sub < 0) { state[tag] = 0; return -1; }
            total += sub;
        }
    }
    state[tag] = 2;
    return total;
}

nmo_fabric *nmo_plant(const nmo_tree *trees, uint32_t ntrees,
                      uint32_t ntags, uint32_t name_span,
                      uint64_t *exit_region) {
    for (uint32_t i = 0; i < ntrees; i++)
        if (nmo_tree_valid(&trees[i], ntags) != 0) return 0;

    const nmo_tree **by_tag = calloc(ntags, sizeof(*by_tag));
    for (uint32_t i = 0; i < ntrees; i++)
        by_tag[trees[i].tag] = &trees[i];
    uint8_t *state = calloc(ntags, 1);
    int *nexit_of = malloc((size_t)ntags * sizeof(int));
    for (uint32_t i = 0; i < ntrees; i++) {
        memset(state, 0, ntags);
        nexit_of[trees[i].tag] =
            chain_exits(by_tag, trees[i].tag, state);
        if (nexit_of[trees[i].tag] < 0) {       /* cycle or dangling */
            free(by_tag); free(state); free(nexit_of);
            return 0;
        }
    }
    free(by_tag); free(state);

    nmo_fabric *f = calloc(1, sizeof(*f));
    f->roads = calloc(ntags, sizeof(nmo_road));
    f->ntags = ntags;
    f->name_span = name_span;
    f->exit_at = exit_region;
    if (name_span) {
        /* only DAG roots receive named arrivals; interior trees are
         * fed nameless values road-to-road and get no matrix */
        uint8_t *targeted = calloc(ntags, 1);
        for (uint32_t i = 0; i < ntrees; i++)
            for (uint16_t p = 0; p < trees[i].nexits; p++)
                if (trees[i].exit_to[p] != NMO_EXIT_BOUNDARY)
                    targeted[trees[i].exit_to[p]] = 1;
        f->matrix_known = calloc((size_t)ntags * name_span, 1);
        int any_multi = 0;
        for (uint32_t i = 0; i < ntrees; i++)
            if (!targeted[trees[i].tag] && nexit_of[trees[i].tag] > 1)
                any_multi = 1;
        if (!any_multi) {
            /* fast layout: matrix[tag*span + name], one conclusion */
            f->matrix_ok = calloc(ntags, 1);
            for (uint32_t i = 0; i < ntrees; i++)
                if (!targeted[trees[i].tag]
                    && nexit_of[trees[i].tag] == 1)
                    f->matrix_ok[trees[i].tag] = 1;
            f->matrix = malloc((size_t)ntags * name_span * 8);
        } else {
            f->matrix_meta = calloc(ntags, 8);
            uint64_t total = 0;
            for (uint32_t i = 0; i < ntrees; i++) {
                uint32_t tag = trees[i].tag;
                int ne = nexit_of[tag];
                if (!targeted[tag] && ne >= 1 && ne <= NMO_MAX_EXITS) {
                    f->matrix_meta[tag] = (total << 4) | (uint64_t)ne;
                    total += (uint64_t)name_span * ne;
                }
            }
            f->matrix = malloc(total * 8);
        }
        free(targeted);
    }

    nmo_tree *copy = calloc(ntrees, sizeof(nmo_tree));
    memcpy(copy, trees, ntrees * sizeof(nmo_tree));
    for (uint32_t i = 0; i < ntrees; i++) {
        uint32_t tag = copy[i].tag;
        f->roads[tag].fn = nmo_walk_road;   /* slow road until paved */
        f->roads[tag].tree = &copy[i];
    }
    free(nexit_of);
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
    free(f->matrix); free(f->matrix_meta);
    free(f->matrix_ok); free(f->matrix_known);
    free(f->roads); free(f);
}
