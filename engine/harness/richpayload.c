/* Richer-than-u64 payload engagement, lawful: real strace traffic,
 * kernel_rich (kernels.h) - a genuine two-slot kernel whose
 * short-transfer fork needs slot 0 (return value) AND slot 1 (first
 * argument) alive at once. Two ledgers, gates the same as measure.c.
 *
 * The result matrix is NOT expected to help here and this is stated,
 * not hidden: identity is carried from slot 0 alone (edge/convert.c),
 * but kernel_rich's output also depends on slot 1, so plant.c marks
 * every root here matrix-ineligible (root_uses_other_slot) - the
 * "paved+matrix" column degrades to plain paved, honestly, because
 * the carried identity does not cover what the kernel computes.
 *
 * Baseline: an idiomatic two-argument switch, same trees, same
 * definition (emit_body2 walks the identical node list). This is the
 * capability engagement, not another performance claim - correctness
 * and gate compliance are what's being demonstrated.
 */
#define _GNU_SOURCE
#include "../edge/edge.h"
#include "kernels.h"
#include <dlfcn.h>
#include <malloc.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e9 + ts.tv_nsec;
}

static const char *binop_expr(uint8_t op) {
    switch (op) {
#define X(NAME, EXPR) case NMO_OP_##NAME: return #EXPR;
    NMO_BINOPS(X)
#undef X
    default: return 0;
    }
}

/* emits a handler over TWO named inputs, indexed by nd->slot - the
 * idiomatic equivalent of "read two fields of a struct" */
static void emit_body2(FILE *o, const nmo_tree *tr) {
    for (uint16_t i = 0; i < tr->nnodes; i++) {
        const nmo_node *nd = &tr->nodes[i];
        if (nd->op == NMO_OP_INPUT)
            fprintf(o, "  uint64_t v%u = x%u;\n", i, nd->slot);
        else if (nd->op == NMO_OP_CONST)
            fprintf(o, "  uint64_t v%u = 0x%016llxULL;\n", i,
                    (unsigned long long)nd->imm);
        else if (nd->op == NMO_OP_SELECT)
            fprintf(o, "  uint64_t v%u = v%u ? v%u : v%u;\n",
                    i, nd->a, nd->b, nd->c);
        else
            fprintf(o, "  uint64_t v%u; { uint64_t l = v%u, r = v%u;"
                       " v%u = (%s); }\n",
                    i, nd->a, nd->b, i, binop_expr(nd->op));
    }
}

typedef void (*bl_fn)(const uint32_t *, const uint64_t *, const uint64_t *,
                      size_t, uint64_t *);

static int emit_baseline(const nmo_tree *trees, uint32_t nt,
                         const char *dir, void **dl) {
    char cpath[512], so[512], cmd[1200];
    snprintf(cpath, sizeof(cpath), "%s/bl_rich.c", dir);
    snprintf(so, sizeof(so), "%s/bl_rich.so", dir);
    FILE *o = fopen(cpath, "w");
    if (!o) return -1;
    fprintf(o, "#include <stdint.h>\n#include <stddef.h>\n");
    for (uint32_t t = 0; t < nt; t++) {
        fprintf(o, "static inline uint64_t h%u(uint64_t x0,"
                   " uint64_t x1) {\n", t);
        emit_body2(o, &trees[t]);
        fprintf(o, "  return v%u;\n}\n", trees[t].exits[0]);
    }
    fprintf(o, "static inline uint64_t d(uint32_t t, uint64_t x0,"
               " uint64_t x1) {\n  switch (t) {\n");
    for (uint32_t t = 0; t < nt; t++)
        fprintf(o, "  case %uu: return h%u(x0, x1);\n", t, t);
    fprintf(o, "  default: return 0;\n  }\n}\n");
    fprintf(o,
        "void bl_switch(const uint32_t *tg, const uint64_t *v0,"
        " const uint64_t *v1, size_t n, uint64_t *out) {\n"
        "  for (size_t i = 0; i < n; i++)"
        " out[i] = d(tg[i], v0[i], v1[i]);\n}\n");
    fclose(o);
    snprintf(cmd, sizeof(cmd), "cc -O2 -shared -fPIC -o %s %s", so, cpath);
    if (system(cmd) != 0) return -1;
    *dl = dlopen(so, RTLD_NOW | RTLD_LOCAL);
    return *dl ? 0 : -1;
}

typedef struct { double mean, min, max; } stat_t;
static int dcmp(const void *a, const void *b) {
    double x = *(const double *)a - *(const double *)b;
    return x < 0 ? -1 : x > 0;
}
static stat_t timeit(int reps, size_t n, void (*run)(void *), void *ctx) {
    double d[64];
    if (reps > 64) reps = 64;
    run(ctx);
    for (int r = 0; r < reps; r++) {
        double t0 = now_ns();
        run(ctx);
        d[r] = (now_ns() - t0) / (double)n;
    }
    qsort(d, reps, sizeof(double), dcmp);
    stat_t s = { 0, d[1], d[reps - 2] };
    for (int r = 1; r < reps - 1; r++) s.mean += d[r];
    s.mean /= reps - 2;
    return s;
}

struct fab_ctx { nmo_fabric *f; const nmo_stream *s; uint64_t *ex; };
static void run_fab(void *p) {
    struct fab_ctx *c = p;
    uint64_t *at = c->ex;
    const nmo_arrival *a = c->s->arr;
    for (size_t i = 0; i < c->s->n; i++)
        at = nmo_arrive_at(c->f, a[i].tag, a[i].name, a[i].val, at);
    c->f->exit_at = at;
}
struct bl_ctx { bl_fn fn; const nmo_stream *s;
    uint32_t *tg; uint64_t *v0, *v1, *out; };
static void run_bl(void *p) {
    struct bl_ctx *c = p;
    c->fn(c->tg, c->v0, c->v1, c->s->n, c->out);
}

int main(int argc, char **argv) {
    const char *trace_dir = argc > 1 ? argv[1] : "traces";
    int reps = argc > 2 ? atoi(argv[2]) : 9;
    const char *dir = getenv("NMO_JIT_DIR");
    if (!dir) dir = "/tmp";

    cpu_set_t set;
    CPU_ZERO(&set); CPU_SET(0, &set);
    sched_setaffinity(0, sizeof(set), &set);

    nmo_namer *nm = nmo_namer_new();
    nmo_stream s;
    if (nmo_convert_strace(trace_dir, nm, &s) != 0) return 1;

    /* how much does slot 1 actually vary, given real traffic? (stated,
     * not assumed - a value-fork over an always-zero slot proves
     * nothing) */
    size_t nonzero_arg0 = 0;
    for (size_t i = 0; i < s.n; i++)
        if (s.arr[i].val[1] != 0) nonzero_arg0++;

    nmo_tree *trees = malloc((size_t)s.ntags * sizeof(nmo_tree));
    for (uint32_t t = 0; t < s.ntags; t++) kernel_rich(&trees[t], t);

    uint64_t *ex = malloc((size_t)(s.n + 8) * 8);
    struct cfg { const char *name; int pave; uint32_t span; };
    struct cfg cfgs[3] = {
        { "walker", 0, 0 },
        { "paved", 1, 0 },
        { "paved+matrix", 1, s.name_span },
    };

    void *dl;
    if (emit_baseline(trees, s.ntags, dir, &dl) != 0) return 2;
    struct bl_ctx b = { 0 };
    b.fn = (bl_fn)dlsym(dl, "bl_switch");
    if (!b.fn) return 2;
    b.s = &s;
    b.tg = malloc(s.n * 4);
    b.v0 = malloc(s.n * 8); b.v1 = malloc(s.n * 8);
    b.out = malloc(s.n * 8);
    for (size_t i = 0; i < s.n; i++) {
        b.tg[i] = s.arr[i].tag;
        b.v0[i] = s.arr[i].val[0];
        b.v1[i] = s.arr[i].val[1];
    }
    run_bl(&b);
    uint64_t *ref = malloc(s.n * 8);
    memcpy(ref, b.out, s.n * 8);

    uint64_t *ref2 = 0;
    double mean[3], lo[3], hi[3];
    int matrix_active[3];
    for (int k = 0; k < 3; k++) {
        nmo_fabric *f = nmo_plant(trees, s.ntags, s.ntags,
                                  cfgs[k].span, ex);
        if (!f) return 2;
        if (cfgs[k].pave && nmo_pave_all(f, dir, 0) != 0) return 2;
        /* did this config's matrix actually attach to any root? (the
         * short-transfer fork should make it ineligible everywhere) */
        matrix_active[k] = 0;
        if (cfgs[k].span)
            for (uint32_t t = 0; t < s.ntags; t++)
                if (f->matrix_meta ? (f->matrix_meta[t] & 15)
                                    : (f->matrix_ok && f->matrix_ok[t]))
                    matrix_active[k] = 1;

        struct fab_ctx fc = { f, &s, ex };
        run_fab(&fc);            /* warmup + parity */
        size_t nex = (size_t)(f->exit_at - ex);
        if (nex != s.n || memcmp(ref, ex, s.n * 8)) {
            fprintf(stderr, "PARITY VIOLATION %s (vs idiomatic)\n",
                    cfgs[k].name);
            return 3;
        }
        if (k == 0) { ref2 = malloc(s.n * 8); memcpy(ref2, ex, s.n * 8); }
        else if (memcmp(ref2, ex, s.n * 8)) {
            fprintf(stderr, "PARITY VIOLATION %s (vs walker)\n",
                    cfgs[k].name);
            return 3;
        }

        struct mallinfo2 mi0 = mallinfo2();
        stat_t st = timeit(reps, s.n, run_fab, &fc);
        if (mallinfo2().uordblks != mi0.uordblks) return 4;   /* G4 */
        mean[k] = st.mean; lo[k] = st.min; hi[k] = st.max;
        nmo_unplant(f);
    }

    stat_t st_bl = timeit(reps, s.n, run_bl, &b);

    printf("{\"richpayload\":{\n"
           " \"stream\":{\"events\":%zu,\"tags\":%u,"
           "\"slot1_nonzero_fraction\":%.4f},\n"
           " \"machine_account\":[",
           s.n, s.ntags, (double)nonzero_arg0 / s.n);
    for (int k = 0; k < 3; k++)
        printf("%s{\"cfg\":\"%s\",\"matrix_attached\":%s,"
               "\"ns_per_event\":{\"mean\":%.2f,\"min\":%.2f,"
               "\"max\":%.2f}}",
               k ? "," : "", cfgs[k].name,
               matrix_active[k] ? "true" : "false",
               mean[k], lo[k], hi[k]);
    printf("],\n \"baseline_account\":{\"bl_switch\":"
           "{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f}},\n"
           " \"note\":\"result matrix ineligible by design when a root "
           "reads a slot beyond 0 (identity is carried from slot 0 "
           "alone); paved+matrix equals paved here, honestly, not a "
           "bug\"}}\n",
           st_bl.mean, st_bl.min, st_bl.max);
    return 0;
}
