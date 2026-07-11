/* Fan-out engagement, lawful: one arrival concludes twice. Entry tree
 * E_t forks - exit 0 feeds boundary tree A_t, exit 1 feeds B_t - so
 * every event yields two boundary exits, in port order.
 *   machine       - fan-out circulation + strided result matrix (a
 *                   recurring name replays BOTH conclusions)
 *   bl_pipeline   - three passes, the fork's two intermediate arrays
 *                   materialized (2n x 8 bytes cross)
 *   bl_fused      - compiled ceiling, one pass
 *   bl_fused_hashed - strongest conventional: fused + hash-memo of
 *                   both outputs
 * Trimmed ranges; coded verdict vs strongest conventional.
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

static void emit_body(FILE *o, const nmo_tree *tr) {
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
}

typedef void (*pl_fn)(const uint32_t *, const uint64_t *, size_t,
                      uint64_t *, uint64_t *, uint64_t *, uint64_t *);
typedef void (*fu_fn)(const uint32_t *, const uint64_t *, size_t,
                      uint64_t *, uint64_t *);
typedef void (*fh_fn)(const uint32_t *, const uint64_t *, size_t,
                      uint64_t *, uint64_t *, uint64_t *, uint64_t *,
                      uint64_t *, uint8_t *);

static int emit_baseline(const nmo_tree *trees, uint32_t T,
                         const char *dir, void **dl) {
    char cpath[512], so[512], cmd[1200];
    snprintf(cpath, sizeof(cpath), "%s/bl_fan.c", dir);
    snprintf(so, sizeof(so), "%s/bl_fan.so", dir);
    FILE *o = fopen(cpath, "w");
    if (!o) return -1;
    fprintf(o, "#include <stdint.h>\n#include <stddef.h>\n");
    for (uint32_t t = 0; t < T; t++) {
        const nmo_tree *tr = &trees[t];
        fprintf(o, "static inline void e%u(uint64_t x, uint64_t *o0,"
                   " uint64_t *o1) {\n", t);
        emit_body(o, tr);
        fprintf(o, "  *o0 = v%u; *o1 = v%u;\n}\n",
                tr->exits[0], tr->exits[1]);
    }
    for (uint32_t i = T; i < 3 * T; i++) {
        fprintf(o, "static inline uint64_t h%u(uint64_t x) {\n",
                trees[i].tag);
        emit_body(o, &trees[i]);
        fprintf(o, "  return v%u;\n}\n", trees[i].exits[0]);
    }
    fprintf(o, "static inline void dE(uint32_t t, uint64_t x,"
               " uint64_t *o0, uint64_t *o1) {\n  switch (t) {\n");
    for (uint32_t t = 0; t < T; t++)
        fprintf(o, "  case %uu: e%u(x, o0, o1); return;\n", t, t);
    fprintf(o, "  default: *o0 = *o1 = 0;\n  }\n}\n");
    for (int side = 0; side < 2; side++) {
        fprintf(o, "static inline uint64_t d%c(uint32_t t, uint64_t x)"
                   " {\n  switch (t) {\n", side ? 'B' : 'A');
        for (uint32_t t = 0; t < T; t++)
            fprintf(o, "  case %uu: return h%u(x);\n", t,
                    (side ? 2 : 1) * T + t);
        fprintf(o, "  default: return 0;\n  }\n}\n");
    }
    fprintf(o,
        "void bl_pipeline(const uint32_t *tg, const uint64_t *vl,"
        " size_t n, uint64_t *e0, uint64_t *e1, uint64_t *o1,"
        " uint64_t *o2) {\n"
        "  for (size_t i = 0; i < n; i++) dE(tg[i], vl[i],"
        " &e0[i], &e1[i]);\n"
        "  for (size_t i = 0; i < n; i++) o1[i] = dA(tg[i], e0[i]);\n"
        "  for (size_t i = 0; i < n; i++) o2[i] = dB(tg[i], e1[i]);\n"
        "}\n"
        "void bl_fused(const uint32_t *tg, const uint64_t *vl,"
        " size_t n, uint64_t *o1, uint64_t *o2) {\n"
        "  for (size_t i = 0; i < n; i++) {\n"
        "    uint64_t a, b;\n"
        "    dE(tg[i], vl[i], &a, &b);\n"
        "    o1[i] = dA(tg[i], a); o2[i] = dB(tg[i], b);\n  }\n}\n"
        "static inline uint64_t mx(uint64_t x) { x ^= x >> 33;"
        " x *= 0xFF51AFD7ED558CCDULL; x ^= x >> 33;"
        " x *= 0xC4CEB9FE1A85EC53ULL; return x ^ (x >> 33); }\n"
        "void bl_fused_hashed(const uint32_t *tg, const uint64_t *vl,"
        " size_t n, uint64_t *o1, uint64_t *o2, uint64_t *hk,"
        " uint64_t *h1, uint64_t *h2, uint8_t *hu) {\n"
        "  for (size_t i = 0; i < n; i++) {\n"
        "    size_t k = (size_t)tg[i] * 4096 + (mx(vl[i]) & 4095);\n"
        "    if (hu[k] && hk[k] == vl[i]) { o1[i] = h1[k];"
        " o2[i] = h2[k]; continue; }\n"
        "    uint64_t a, b;\n"
        "    dE(tg[i], vl[i], &a, &b);\n"
        "    uint64_t r1 = dA(tg[i], a), r2 = dB(tg[i], b);\n"
        "    o1[i] = r1; o2[i] = r2;\n"
        "    hk[k] = vl[i]; h1[k] = r1; h2[k] = r2; hu[k] = 1;\n"
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
struct bl_ctx { pl_fn pl; fu_fn fu; fh_fn fh; const nmo_stream *s;
    uint32_t *tg; uint64_t *vl, *e0, *e1, *o1, *o2, *hk, *h1, *h2;
    uint8_t *hu; };
static void run_pl(void *p) {
    struct bl_ctx *c = p;
    c->pl(c->tg, c->vl, c->s->n, c->e0, c->e1, c->o1, c->o2);
}
static void run_fu(void *p) {
    struct bl_ctx *c = p;
    c->fu(c->tg, c->vl, c->s->n, c->o1, c->o2);
}
static void run_fh(void *p) {
    struct bl_ctx *c = p;
    c->fh(c->tg, c->vl, c->s->n, c->o1, c->o2, c->hk, c->h1, c->h2,
          c->hu);
}

int main(int argc, char **argv) {
    const char *trace_dir = argc > 1 ? argv[1] : "traces";
    int reps = argc > 2 ? atoi(argv[2]) : 15;
    const char *dir = getenv("NMO_JIT_DIR");
    if (!dir) dir = "/tmp";

    cpu_set_t set;
    CPU_ZERO(&set); CPU_SET(0, &set);
    sched_setaffinity(0, sizeof(set), &set);

    nmo_namer *nm = nmo_namer_new();
    nmo_stream s;
    if (nmo_convert_strace(trace_dir, nm, &s) != 0) return 1;
    uint32_t T = s.ntags;

    /* E_t forks to A_t (T+t) and B_t (2T+t), both boundary */
    nmo_tree *trees = malloc((size_t)3 * T * sizeof(nmo_tree));
    for (uint32_t t = 0; t < T; t++) {
        kernel_fan2(&trees[t], t, t, T + t, 2 * T + t);
        kernel_wired(&trees[T + t], T + t, 0x300000u ^ t,
                     NMO_EXIT_BOUNDARY);
        kernel_wired(&trees[2 * T + t], 2 * T + t, 0x400000u ^ t,
                     NMO_EXIT_BOUNDARY);
    }

    uint64_t *ex = malloc((size_t)(2 * s.n + 8) * 8);
    nmo_fabric *f = nmo_plant(trees, 3 * T, 3 * T, s.name_span, ex);
    if (!f) return 2;
    double p0 = now_ns();
    if (nmo_pave_all(f, dir, 0) != 0) return 2;
    double paving_ms = (now_ns() - p0) / 1e6;
    uint64_t *ex2 = malloc((size_t)(2 * s.n + 8) * 8);
    nmo_fabric *f0 = nmo_plant(trees, 3 * T, 3 * T, 0, ex2);
    if (!f0 || nmo_pave_all(f0, dir, 0) != 0) return 2;

    void *dl;
    p0 = now_ns();
    if (emit_baseline(trees, T, dir, &dl) != 0) return 2;
    double bl_build_ms = (now_ns() - p0) / 1e6;
    struct bl_ctx b = { 0 };
    b.pl = (pl_fn)dlsym(dl, "bl_pipeline");
    b.fu = (fu_fn)dlsym(dl, "bl_fused");
    b.fh = (fh_fn)dlsym(dl, "bl_fused_hashed");
    if (!b.pl || !b.fu || !b.fh) return 2;
    b.s = &s;
    b.tg = malloc(s.n * 4); b.vl = malloc(s.n * 8);
    b.e0 = malloc(s.n * 8); b.e1 = malloc(s.n * 8);
    b.o1 = malloc(s.n * 8); b.o2 = malloc(s.n * 8);
    b.hk = malloc((size_t)T * 4096 * 8);
    b.h1 = malloc((size_t)T * 4096 * 8);
    b.h2 = malloc((size_t)T * 4096 * 8);
    b.hu = calloc((size_t)T * 4096, 1);
    for (size_t i = 0; i < s.n; i++) {
        b.tg[i] = s.arr[i].tag;
        b.vl[i] = s.arr[i].val;
    }

    /* parity: machine exits interleave [A, B] per arrival */
    run_fu(&b);
    struct fab_ctx fc = { f, &s, ex }, fc0 = { f0, &s, ex2 };
    run_fab(&fc);
    if ((size_t)(f->exit_at - ex) != 2 * s.n) return 3;
    for (size_t i = 0; i < s.n; i++)
        if (ex[2 * i] != b.o1[i] || ex[2 * i + 1] != b.o2[i]) {
            fprintf(stderr, "PARITY VIOLATION machine @%zu\n", i);
            return 3;
        }
    run_pl(&b);
    for (size_t i = 0; i < s.n; i++)
        if (ex[2 * i] != b.o1[i] || ex[2 * i + 1] != b.o2[i]) return 3;
    run_fh(&b);
    for (size_t i = 0; i < s.n; i++)
        if (ex[2 * i] != b.o1[i] || ex[2 * i + 1] != b.o2[i]) return 3;
    run_fab(&fc0);
    if (memcmp(ex, ex2, 2 * s.n * 8)) return 3;

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

    printf("{\"fanout\":{\n"
           " \"stream\":{\"events\":%zu,\"entry_tags\":%u,\"trees\":%u,"
           "\"exits_per_event\":2},\n"
           " \"machine_account\":{"
           "\"circulating\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f},"
           "\"circulating+matrix\":{\"mean\":%.2f,\"min\":%.2f,"
           "\"max\":%.2f},\"intermediate_boundary_bytes\":0},\n"
           " \"baseline_account\":{"
           "\"bl_pipeline\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f,"
           "\"intermediate_boundary_bytes\":%zu},"
           "\"bl_fused\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f},"
           "\"bl_fused_hashed\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f}},\n"
           " \"emulation_account\":{\"paving_ms\":%.1f,"
           "\"baseline_build_ms\":%.1f},\n"
           " \"opponent\":\"%s\",\"verdict\":\"%s\"}}\n",
           s.n, T, 3 * T,
           st_m0.mean, st_m0.min, st_m0.max,
           st_mm.mean, st_mm.min, st_mm.max,
           st_pl.mean, st_pl.min, st_pl.max, (size_t)s.n * 16,
           st_fu.mean, st_fu.min, st_fu.max,
           st_fh.mean, st_fh.min, st_fh.max,
           paving_ms, bl_build_ms, opp_name, verdict);
    return 0;
}
