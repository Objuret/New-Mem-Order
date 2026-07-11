/* The fabric's two functions. That is the point: there is nothing
 * here for administration to live in. */
#include "fabric.h"

void nmo_arrive(nmo_fabric *f, uint32_t tag, uint32_t name, uint64_t x) {
    nmo_arrive_inl(f, tag, name, x);
}

/* The dispatch primitive, as its own symbol: edge handoff to road
 * entry, whole function. G1's instruction budget is asserted against
 * THIS - the thing the gate polices is that arrival->road stays one
 * indirect hop with nothing living around it. nmo_arrive_at uses the
 * identical construct inline; its other paths are layer-5 replay
 * (conclusions that never reach a road), not dispatch. */
void nmo_road_entry(nmo_fabric *f, uint32_t tag, uint64_t x) {
    nmo_road *r = &f->roads[tag];
    r->fn(f, r->tree, x);
}

/* The single slow road (layer 1): one operation at a time over the
 * tree form. Novel shapes are answered here while the edge paves
 * them; if no paver exists, this road serves forever, correctly. */
void nmo_walk_road(nmo_fabric *f, const nmo_tree *t, uint64_t x) {
    uint64_t vals[NMO_MAX_NODES];
    for (uint16_t i = 0; i < t->nnodes; i++) {
        const nmo_node *nd = &t->nodes[i];
        uint64_t v;
        switch (nd->op) {
        case NMO_OP_INPUT: v = x; break;
        case NMO_OP_CONST: v = nd->imm; break;
        case NMO_OP_SELECT:
            v = vals[nd->a] ? vals[nd->b] : vals[nd->c]; break;
#define X(NAME, EXPR) \
        case NMO_OP_##NAME: { \
            uint64_t l = vals[nd->a], r = vals[nd->b]; \
            v = (EXPR); } break;
        NMO_BINOPS(X)
#undef X
        default: v = 0; break;
        }
        vals[i] = v;
    }
    for (uint16_t p = 0; p < t->nexits; p++) {
        uint64_t v = vals[t->exits[p]];
        uint32_t to = t->exit_to[p];
        if (to == NMO_EXIT_BOUNDARY) {
            /* only exits are sent (layer 5): a bare value, in order */
            *f->exit_at++ = v;
        } else {
            /* trees feed trees inside residence (layer 4): the value
             * moves road-to-road without a name, without an address,
             * without crossing anything */
            nmo_road *r = &f->roads[to];
            r->fn(f, r->tree, v);
        }
    }
}
