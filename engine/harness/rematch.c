/* Niche rematch, lawful: same real stream, same kernels (one tree
 * definition), fabric vs the strongest conventional opponent:
 *   bl_switch - the trees emitted as inline C handlers behind one
 *               switch, whole loop compiled -O2 in a .so
 *   bl_named  - bl_switch behind a name-indexed cache (the baseline
 *               gets the machine's own memo idea, free)
 * Coded verdict: WIN / LOSS / INCONCLUSIVE on non-overlapping ranges,
 * full machine (paved+matrix) vs strongest baseline. Two ledgers.
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

typedef void (*bl_fn)(const uint32_t *, const uint64_t *, size_t,
                      uint64_t *);
typedef void (*bln_fn)(const uint32_t *, const uint64_t *,
                       const uint32_t *, size_t, uint64_t *,
                       uint64_t *, uint8_t *, uint32_t);
typedef void (*blh_fn)(const uint32_t *, const uint64_t *, size_t,
                       uint64_t *, uint64_t *, uint64_t *, uint8_t *);

/* emit the baseline: same trees, idiomatic inline switch, -O2 */
static int emit_baseline(const nmo_tree *trees, uint32_t nt,
                         const char *dir, void **dl) {
    char cpath[512], so[512], cmd[1200];
    snprintf(cpath, sizeof(cpath), "%s/baseline.c", dir);
    snprintf(so, sizeof(so), "%s/baseline.so", dir);
    FILE *o = fopen(cpath, "w");
    if (!o) return -1;
    fprintf(o, "#include <stdint.h>\n#include <stddef.h>\n");
    for (uint32_t t = 0; t < nt; t++) {
        const nmo_tree *tr = &trees[t];
        fprintf(o, "static inline uint64_t h%u(uint64_t x) {\n", t);
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
                fprintf(o, "  uint64_t v%u; { uint64_t l = v%u,"
                           " r = v%u; v%u = (%s); }\n",
                        i, nd->a, nd->b, i, binop_expr(nd->op));
        }
        fprintf(o, "  return v%u;\n}\n", tr->exits[0]);
    }
    fprintf(o, "static inline uint64_t d(uint32_t t, uint64_t x)"
               " {\n  switch (t) {\n");
    for (uint32_t t = 0; t < nt; t++)
        fprintf(o, "  case %uu: return h%u(x);\n", t, t);
    fprintf(o, "  default: return 0;\n  }\n}\n");
    fprintf(o,
        "void bl_switch(const uint32_t *tg, const uint64_t *vl,"
        " size_t n, uint64_t *out) {\n"
        "  for (size_t i = 0; i < n; i++) out[i] = d(tg[i], vl[i]);\n"
        "}\n"
        "static inline uint64_t mx(uint64_t x) { x ^= x >> 33;"
        " x *= 0xFF51AFD7ED558CCDULL; x ^= x >> 33;"
        " x *= 0xC4CEB9FE1A85EC53ULL; return x ^ (x >> 33); }\n"
        "void bl_hashed(const uint32_t *tg, const uint64_t *vl,"
        " size_t n, uint64_t *out, uint64_t *hk, uint64_t *hv,"
        " uint8_t *hu) {\n"
        "  for (size_t i = 0; i < n; i++) {\n"
        "    size_t k = (size_t)tg[i] * 4096 + (mx(vl[i]) & 4095);\n"
        "    if (hu[k] && hk[k] == vl[i]) { out[i] = hv[k]; continue; }\n"
        "    uint64_t r = d(tg[i], vl[i]);\n"
        "    out[i] = r; hk[k] = vl[i]; hv[k] = r; hu[k] = 1;\n"
        "  }\n}\n"
        "void bl_named(const uint32_t *tg, const uint64_t *vl,"
        " const uint32_t *nm, size_t n, uint64_t *out,"
        " uint64_t *cache, uint8_t *known, uint32_t span) {\n"
        "  for (size_t i = 0; i < n; i++) {\n"
        "    size_t k = (size_t)tg[i] * span + nm[i];\n"
        "    if (nm[i] < span && known[k]) { out[i] = cache[k];"
        " continue; }\n"
        "    uint64_t r = d(tg[i], vl[i]);\n"
        "    out[i] = r;\n"
        "    if (nm[i] < span) { cache[k] = r; known[k] = 1; }\n"
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
/* symmetric trim (as in circulate): best and worst rep of EVERY
 * variant dropped before ranges compare; declared pre-verdict */
static stat_t timeit(int reps, size_t n, void (*run)(void *), void *ctx) {
    double d[64];
    if (reps > 64) reps = 64;
    run(ctx);                     /* self-warm */
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
static void run_fabric(void *p) {
    struct fab_ctx *c = p;
    uint64_t *at = c->ex;
    const nmo_arrival *a = c->s->arr;
    for (size_t i = 0; i < c->s->n; i++)
        at = nmo_arrive_at(c->f, a[i].tag, a[i].name, a[i].val, at);
    c->f->exit_at = at;
}
struct bl_ctx { bl_fn fn; bln_fn fnn; blh_fn fnh; const nmo_stream *s;
    uint32_t *tg; uint64_t *vl; uint32_t *nm; uint64_t *out;
    uint64_t *cache; uint8_t *known; uint32_t span;
    uint64_t *hk, *hv; uint8_t *hu; };
static void run_bl(void *p) {
    struct bl_ctx *c = p;
    c->fn(c->tg, c->vl, c->s->n, c->out);
}
static void run_blh(void *p) {
    struct bl_ctx *c = p;
    c->fnh(c->tg, c->vl, c->s->n, c->out, c->hk, c->hv, c->hu);
}
static void run_bln(void *p) {
    struct bl_ctx *c = p;
    c->fnn(c->tg, c->vl, c->nm, c->s->n, c->out, c->cache, c->known,
           c->span);
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

    nmo_tree *trees = malloc((size_t)s.ntags * sizeof(nmo_tree));
    for (uint32_t t = 0; t < s.ntags; t++) kernel(&trees[t], t);

    /* fabric, full machine */
    uint64_t *ex = malloc((size_t)(s.n + 8) * 8);
    nmo_fabric *f = nmo_plant(trees, s.ntags, s.ntags, s.name_span, ex);
    double p0 = now_ns();
    if (nmo_pave_all(f, dir, 0) != 0) return 2;
    double paving_ms = (now_ns() - p0) / 1e6;

    /* baseline .so from the same trees */
    void *dl;
    p0 = now_ns();
    if (emit_baseline(trees, s.ntags, dir, &dl) != 0) return 2;
    double bl_build_ms = (now_ns() - p0) / 1e6;
    struct bl_ctx b = { 0 };
    b.fn = (bl_fn)dlsym(dl, "bl_switch");
    b.fnn = (bln_fn)dlsym(dl, "bl_named");
    b.fnh = (blh_fn)dlsym(dl, "bl_hashed");
    if (!b.fn || !b.fnn || !b.fnh) return 2;
    b.s = &s;
    b.tg = malloc(s.n * 4); b.vl = malloc(s.n * 8);
    b.nm = malloc(s.n * 4); b.out = malloc(s.n * 8);
    b.span = s.name_span;
    b.cache = malloc((size_t)s.ntags * s.name_span * 8);
    b.known = calloc((size_t)s.ntags * s.name_span, 1);
    b.hk = malloc((size_t)s.ntags * 4096 * 8);
    b.hv = malloc((size_t)s.ntags * 4096 * 8);
    b.hu = calloc((size_t)s.ntags * 4096, 1);
    for (size_t i = 0; i < s.n; i++) {
        b.tg[i] = s.arr[i].tag;
        b.vl[i] = s.arr[i].val;
        b.nm[i] = s.arr[i].name;
    }

    struct fab_ctx fc = { f, &s, ex };
    /* warmup + parity, all four */
    run_bl(&b);
    uint64_t *ref = malloc(s.n * 8);
    memcpy(ref, b.out, s.n * 8);
    run_bln(&b);
    if (memcmp(ref, b.out, s.n * 8)) return 3;
    run_blh(&b);
    if (memcmp(ref, b.out, s.n * 8)) return 3;
    run_fabric(&fc);
    if ((size_t)(f->exit_at - ex) != s.n || memcmp(ref, ex, s.n * 8)) {
        fprintf(stderr, "PARITY VIOLATION fabric\n");
        return 3;
    }

    struct mallinfo2 mi0 = mallinfo2();
    stat_t st_sw = timeit(reps, s.n, run_bl, &b);
    stat_t st_hs = timeit(reps, s.n, run_blh, &b);
    stat_t st_bn = timeit(reps, s.n, run_bln, &b);
    stat_t st_fb = timeit(reps, s.n, run_fabric, &fc);
    if (mallinfo2().uordblks != mi0.uordblks) return 4;   /* G4 */

    /* opponents are systems constructible WITHOUT the machine's edge:
     * the switch, and the hash-memoized switch (it pays identity
     * computation, the honest conventional price). bl_named consumes
     * the edge's carried names - it is an ablation of the machine
     * (edge + flat loop, no fabric), reported as such. */
    stat_t opp = st_sw.mean <= st_hs.mean ? st_sw : st_hs;
    const char *opp_name = st_sw.mean <= st_hs.mean
                           ? "bl_switch" : "bl_hashed";
    const char *verdict =
        st_fb.max < opp.min ? "WIN"
        : opp.max < st_fb.min ? "LOSS" : "INCONCLUSIVE";

    printf("{\"niche_rematch\":{\n"
           " \"stream\":{\"events\":%zu,\"tags\":%u,"
           "\"entropy_before\":%.3f,\"entropy_after\":%.3f},\n"
           " \"machine_account\":{\"paved+matrix\":"
           "{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f}},\n"
           " \"baseline_account\":{"
           "\"bl_switch\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f},"
           "\"bl_hashed\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f}},\n"
           " \"ablation_no_fabric\":{"
           "\"bl_named\":{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f}},\n"
           " \"emulation_account\":{\"paving_ms\":%.1f,"
           "\"baseline_build_ms\":%.1f},\n"
           " \"opponent\":\"%s\",\"verdict\":\"%s\"}}\n",
           s.n, s.ntags, s.entropy_before, s.entropy_after,
           st_fb.mean, st_fb.min, st_fb.max,
           st_sw.mean, st_sw.min, st_sw.max,
           st_hs.mean, st_hs.min, st_hs.max,
           st_bn.mean, st_bn.min, st_bn.max,
           paving_ms, bl_build_ms, opp_name, verdict);
    return 0;
}
