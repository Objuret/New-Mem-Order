/* Circulation engagement, lawful: every event runs a 3-stage chain
 * (same tree definitions on all sides).
 *   machine      - trees feed trees inside the fabric; intermediates
 *                  die in registers; whole-chain result matrix under
 *                  the entry name (carried identity)
 *   bl_pipeline  - the fragmented-system architecture: each stage a
 *                  separate compiled pass, intermediates materialized
 *                  to arrays that cross the memory boundary
 *   bl_fused     - the compiled ceiling: all stages inlined into one
 *                  handler (possible only when every stage lives in
 *                  one program at compile time)
 *   bl_fused_hashed - the strongest conventional: fused + hash-memo
 *                  (pays identity computation per event)
 * Coded verdict: machine vs strongest conventional, disjoint ranges.
 * Intermediate-boundary bytes counted on both sides.
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

static void emit_handler(FILE *o, const nmo_tree *tr, uint32_t id) {
    fprintf(o, "static inline uint64_t h%u(uint64_t x) {\n", id);
    for (uint16_t i = 0; i < tr->nnodes; i++) {
        const nmo_node *nd = &tr->nodes[i];
        if (nd->op == NMO_OP_INPUT)
            fprintf(o, "  uint64_t v%u = x;\n", i);
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
    fprintf(o, "  return v%u;\n}\n", tr->exits[0]);
}

typedef void (*pl_fn)(const uint32_t *, const uint64_t *, size_t,
                      uint64_t *, uint64_t *, uint64_t *);
typedef void (*fu_fn)(const uint32_t *, const uint64_t *, size_t,
                      uint64_t *);
typedef void (*fh_fn)(const uint32_t *, const uint64_t *, size_t,
                      uint64_t *, uint64_t *, uint64_t *, uint8_t *);

static int emit_baseline(const nmo_tree *trees, uint32_t T, int S,
                         const char *dir, void **dl) {
    char cpath[512], so[512], cmd[1200];
    snprintf(cpath, sizeof(cpath), "%s/bl_circ.c", dir);
    snprintf(so, sizeof(so), "%s/bl_circ.so", dir);
    FILE *o = fopen(cpath, "w");
    if (!o) return -1;
    fprintf(o, "#include <stdint.h>\n#include <stddef.h>\n");
    for (uint32_t i = 0; i < (uint32_t)S * T; i++)
        emit_handler(o, &trees[i], trees[i].tag);
    for (int st = 0; st < S; st++) {
        fprintf(o, "static inline uint64_t d%d(uint32_t t, uint64_t x)"
                   " {\n  switch (t) {\n", st);
        for (uint32_t t = 0; t < T; t++)
            fprintf(o, "  case %uu: return h%u(x);\n", t,
                    (uint32_t)st * T + t);
        fprintf(o, "  default: return 0;\n  }\n}\n");
    }
    /* pipeline: S separate passes, S-1 materialized arrays */
    fprintf(o,
        "void bl_pipeline(const uint32_t *tg, const uint64_t *vl,"
        " size_t n, uint64_t *i1, uint64_t *i2, uint64_t *out) {\n");
    for (int st = 0; st < S; st++) {
        const char *src = st == 0 ? "vl" : (st % 2 ? "i1" : "i2");
        const char *dst = st == S - 1 ? "out" : (st % 2 ? "i2" : "i1");
        fprintf(o, "  for (size_t i = 0; i < n; i++) %s[i] ="
                   " d%d(tg[i], %s[i]);\n", dst, st, src);
    }
    fprintf(o, "}\n");
    fprintf(o,
        "void bl_fused(const uint32_t *tg, const uint64_t *vl,"
        " size_t n, uint64_t *out) {\n"
        "  for (size_t i = 0; i < n; i++) {\n"
        "    uint64_t x = vl[i];\n");
    for (int st = 0; st < S; st++)
        fprintf(o, "    x = d%d(tg[i], x);\n", st);
    fprintf(o, "    out[i] = x;\n  }\n}\n");
    fprintf(o,
        "static inline uint64_t mx(uint64_t x) { x ^= x >> 33;"
        " x *= 0xFF51AFD7ED558CCDULL; x ^= x >> 33;"
        " x *= 0xC4CEB9FE1A85EC53ULL; return x ^ (x >> 33); }\n"
        "void bl_fused_hashed(const uint32_t *tg, const uint64_t *vl,"
        " size_t n, uint64_t *out, uint64_t *hk, uint64_t *hv,"
        " uint8_t *hu) {\n"
        "  for (size_t i = 0; i < n; i++) {\n"
        "    size_t k = (size_t)tg[i] * 4096 + (mx(vl[i]) & 4095);\n"
        "    if (hu[k] && hk[k] == vl[i]) { out[i] = hv[k]; continue; }\n"
        "    uint64_t x = vl[i];\n");
    for (int st = 0; st < S; st++)
        fprintf(o, "    x = d%d(tg[i], x);\n", st);
    fprintf(o,
        "    out[i] = x; hk[k] = vl[i]; hv[k] = x; hu[k] = 1;\n"
        "  }\n}\n");
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
/* symmetric trim: the single best and worst rep of EVERY variant are
 * dropped before ranges are compared - declared here, applied to both
 * sides, decided before any verdict is read */
static stat_t timeit(int reps, size_t n, void (*run)(void *), void *ctx) {
    double d[64];
    if (reps > 64) reps = 64;
    run(ctx);                                   /* self-warm */
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
struct bl_ctx { pl_fn pl; fu_fn fu; fh_fn fh; const nmo_stream *s;
    uint32_t *tg; uint64_t *vl, *i1, *i2, *out, *hk, *hv;
    uint8_t *hu; };
static void run_pl(void *p) {
    struct bl_ctx *c = p;
    c->pl(c->tg, c->vl, c->s->n, c->i1, c->i2, c->out);
}
static void run_fu(void *p) {
    struct bl_ctx *c = p;
    c->fu(c->tg, c->vl, c->s->n, c->out);
}
static void run_fh(void *p) {
    struct bl_ctx *c = p;
    c->fh(c->tg, c->vl, c->s->n, c->out, c->hk, c->hv, c->hu);
}

int main(int argc, char **argv) {
    const char *trace_dir = argc > 1 ? argv[1] : "traces";
    int reps = argc > 2 ? atoi(argv[2]) : 9;
    int S = argc > 3 ? atoi(argv[3]) : 3;
    if (S < 1 || S > 16) return 1;
    const char *dir = getenv("NMO_JIT_DIR");
    if (!dir) dir = "/tmp";

    cpu_set_t set;
    CPU_ZERO(&set); CPU_SET(0, &set);
    sched_setaffinity(0, sizeof(set), &set);

    nmo_namer *nm = nmo_namer_new();
    nmo_stream s;
    if (nmo_convert_strace(trace_dir, nm, &s) != 0) return 1;
    uint32_t T = s.ntags;

    /* S-stage chains: entry t -> T+t -> ... -> (S-1)T+t -> boundary */
    nmo_tree *trees = malloc((size_t)S * T * sizeof(nmo_tree));
    for (uint32_t t = 0; t < T; t++)
        for (int st = 0; st < S; st++)
            kernel_wired(&trees[st * T + t], st * T + t,
                         ((uint32_t)st << 20) ^ t,
                         st == S - 1 ? NMO_EXIT_BOUNDARY
                                     : (st + 1) * T + t);

    uint64_t *ex = malloc((size_t)(s.n + 8) * 8);
    nmo_fabric *f = nmo_plant(trees, S * T, S * T, s.name_span, ex);
    if (!f) { fprintf(stderr, "plant failed\n"); return 2; }
    double p0 = now_ns();
    if (nmo_pave_all(f, dir, 0) != 0) return 2;
    double paving_ms = (now_ns() - p0) / 1e6;
    /* pure circulation (no matrix) fabric for the ablation column */
    uint64_t *ex2 = malloc((size_t)(s.n + 8) * 8);
    nmo_fabric *f0 = nmo_plant(trees, S * T, S * T, 0, ex2);
    if (!f0 || nmo_pave_all(f0, dir, 0) != 0) return 2;

    void *dl;
    p0 = now_ns();
    if (emit_baseline(trees, T, S, dir, &dl) != 0) return 2;
    double bl_build_ms = (now_ns() - p0) / 1e6;
    struct bl_ctx b = { 0 };
    b.pl = (pl_fn)dlsym(dl, "bl_pipeline");
    b.fu = (fu_fn)dlsym(dl, "bl_fused");
    b.fh = (fh_fn)dlsym(dl, "bl_fused_hashed");
    if (!b.pl || !b.fu || !b.fh) return 2;
    b.s = &s;
    b.tg = malloc(s.n * 4); b.vl = malloc(s.n * 8);
    b.i1 = malloc(s.n * 8); b.i2 = malloc(s.n * 8);
    b.out = malloc(s.n * 8);
    b.hk = malloc((size_t)T * 4096 * 8);
    b.hv = malloc((size_t)T * 4096 * 8);
    b.hu = calloc((size_t)T * 4096, 1);
    for (size_t i = 0; i < s.n; i++) {
        b.tg[i] = s.arr[i].tag;
        b.vl[i] = s.arr[i].val[0];
    }

    /* parity, all five */
    run_fu(&b);
    uint64_t *ref = malloc(s.n * 8);
    memcpy(ref, b.out, s.n * 8);
    run_pl(&b);
    if (memcmp(ref, b.out, s.n * 8)) return 3;
    run_fh(&b);
    if (memcmp(ref, b.out, s.n * 8)) return 3;
    struct fab_ctx fc = { f, &s, ex }, fc0 = { f0, &s, ex2 };
    run_fab(&fc);
    if ((size_t)(f->exit_at - ex) != s.n || memcmp(ref, ex, s.n * 8)) {
        fprintf(stderr, "PARITY VIOLATION machine\n");
        return 3;
    }
    run_fab(&fc0);
    if (memcmp(ref, ex2, s.n * 8)) return 3;

    struct mallinfo2 mi0 = mallinfo2();
    stat_t st_pl = timeit(reps, s.n, run_pl, &b);
    stat_t st_fu = timeit(reps, s.n, run_fu, &b);
    stat_t st_fh = timeit(reps, s.n, run_fh, &b);
    stat_t st_m0 = timeit(reps, s.n, run_fab, &fc0);
    stat_t st_mm = timeit(reps, s.n, run_fab, &fc);
    if (mallinfo2().uordblks != mi0.uordblks) return 4;   /* G4 */

    stat_t opp = st_pl;
    const char *opp_name = "bl_pipeline";
    if (st_fu.mean < opp.mean) { opp = st_fu; opp_name = "bl_fused"; }
    if (st_fh.mean < opp.mean) { opp = st_fh; opp_name = "bl_fused_hashed"; }
    const char *verdict =
        st_mm.max < opp.min ? "WIN"
        : opp.max < st_mm.min ? "LOSS" : "INCONCLUSIVE";

    printf("{\"circulation\":{\n"
           " \"stream\":{\"events\":%zu,\"entry_tags\":%u,\"stages\":%d,"
           "\"trees\":%u,\"entropy_before\":%.3f,\"entropy_after\":%.3f},\n"
           " \"machine_account\":{"
           "\"circulating\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f},"
           "\"circulating+matrix\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f},"
           "\"intermediate_boundary_bytes\":0},\n"
           " \"baseline_account\":{"
           "\"bl_pipeline\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f,"
           "\"intermediate_boundary_bytes\":%zu},"
           "\"bl_fused\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f},"
           "\"bl_fused_hashed\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f}},\n"
           " \"emulation_account\":{\"paving_ms\":%.1f,"
           "\"baseline_build_ms\":%.1f},\n"
           " \"opponent\":\"%s\",\"verdict\":\"%s\"}}\n",
           s.n, T, S, S * T, s.entropy_before, s.entropy_after,
           st_m0.mean, st_m0.min, st_m0.max,
           st_mm.mean, st_mm.min, st_mm.max,
           st_pl.mean, st_pl.min, st_pl.max, (size_t)s.n * 8 * (S - 1),
           st_fu.mean, st_fu.min, st_fu.max,
           st_fh.mean, st_fh.min, st_fh.max,
           paving_ms, bl_build_ms, opp_name, verdict);
    return 0;
}
