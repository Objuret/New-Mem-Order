/* Paving: validated trees become straight-line machine code via cc +
 * dlopen, once. Cost is real, measured, and reported by harnesses in
 * the emulation ledger. Failure leaves the walker serving - correct,
 * just slow. */
#define _GNU_SOURCE
#include "edge.h"
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>

static const char *binop_expr(uint8_t op) {
    switch (op) {
#define X(NAME, EXPR) case NMO_OP_##NAME: return #EXPR;
    NMO_BINOPS(X)
#undef X
    default: return 0;
    }
}

static void emit_road(FILE *o, const nmo_tree *t) {
    fprintf(o, "void nmo_paved_%u(nmo_fabric *f, const nmo_tree *t,"
               " const uint64_t *x) {\n  (void)t;\n", t->tag);
    for (uint16_t i = 0; i < t->nnodes; i++) {
        const nmo_node *nd = &t->nodes[i];
        switch (nd->op) {
        case NMO_OP_INPUT:
            fprintf(o, "  uint64_t v%u = x[%u];\n", i, nd->slot); break;
        case NMO_OP_CONST:
            fprintf(o, "  uint64_t v%u = 0x%016llxULL;\n", i,
                    (unsigned long long)nd->imm); break;
        case NMO_OP_SELECT:
            fprintf(o, "  uint64_t v%u = v%u ? v%u : v%u;\n",
                    i, nd->a, nd->b, nd->c); break;
        default:
            fprintf(o, "  uint64_t v%u; { uint64_t l = v%u, r = v%u;"
                       " v%u = (%s); }\n",
                    i, nd->a, nd->b, i, binop_expr(nd->op));
        }
    }
    for (uint16_t p = 0; p < t->nexits; p++) {
        uint32_t to = t->exit_to[p];
        if (to == NMO_EXIT_BOUNDARY)
            fprintf(o, "  *f->exit_at++ = v%u;\n", t->exits[p]);
        else
            fprintf(o, "  { uint64_t next%u[%d] = { v%u };"
                       " nmo_road *r = &f->roads[%uu];"
                       " r->fn(f, r->tree, next%u); }\n",
                    p, NMO_MAX_SLOTS, t->exits[p], to, p);
    }
    fprintf(o, "}\n");
}

int nmo_pave_all(nmo_fabric *f, const char *dir, const char *cc) {
    char cpath[512], so[512], cmd[1400];
    snprintf(cpath, sizeof(cpath), "%s/roads.c", dir);
    snprintf(so, sizeof(so), "%s/roads.so", dir);
    FILE *o = fopen(cpath, "w");
    if (!o) return -1;
    fprintf(o, "#include \"fabric.h\"\n");
    for (uint32_t t = 0; t < f->ntags; t++)
        if (f->roads[t].tree)
            emit_road(o, f->roads[t].tree);
    fclose(o);
    /* road-residency flags: straight-line single-block roads gain
     * nothing from -O2-over--Os or 16B function alignment, and each
     * road is entered indirectly through the table, so per-function
     * padding and CFI landing pads are pure resident fat. NMO_PAVE_
     * FLAGS overrides for experiments; the default is the measured
     * Pareto point (size down, rematch speed unchanged - see
     * results/residency_v1.json history). */
    const char *flags = getenv("NMO_PAVE_FLAGS");
    if (!flags)
        flags = "-Os -falign-functions=1 -fcf-protection=none";
    snprintf(cmd, sizeof(cmd),
             "%s %s -shared -fPIC -I%s -o %s %s 2>/dev/null",
             cc ? cc : "cc", flags, FABRIC_INC, so, cpath);
    if (system(cmd) != 0) return -1;
    void *dl = dlopen(so, RTLD_NOW | RTLD_LOCAL);
    if (!dl) return -1;
    int paved = 0;
    for (uint32_t t = 0; t < f->ntags; t++) {
        if (!f->roads[t].tree) continue;
        char sym[64];
        snprintf(sym, sizeof(sym), "nmo_paved_%u", t);
        nmo_road_fn fn = (nmo_road_fn)dlsym(dl, sym);
        if (fn) { f->roads[t].fn = fn; paved++; }
    }
    return paved == 0 ? -1 : 0;
}
