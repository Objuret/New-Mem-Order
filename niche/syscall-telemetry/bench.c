/* The niche head-to-head: real syscall traffic from real programs,
 * one enrichment computation, five executions:
 *
 *   bl_switch    - idiomatic compiled C: inlined switch dispatch.
 *   bl_memo      - the strongest conventional baseline: the same
 *                  switch behind a per-tag direct-mapped memo table
 *                  with the same geometry the engine uses. Guarantee
 *                  parity of technique, not just of results.
 *   eng_plan     - the engine, plan circulation + result matrix.
 *   eng_jit      - the full machine: jit-paved roads + result matrix.
 *   eng_jit_nm   - jit roads, result matrix off (isolates what the
 *                  memo contributes on this traffic).
 *
 * All five produce identical outputs (checked, abort on mismatch).
 * Warmup pass first (arrival = paving; memo tables reach steady
 * state), then interleaved timed reps over the whole real stream.
 * Paving cost is reported separately - it is real and amortized, and
 * it is not hidden inside the steady-state numbers.
 */
#define _GNU_SOURCE
#include "../../engine/nmo.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sched.h>

static double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e9 + ts.tv_nsec;
}

#include "shapes.h"

#define MEMO 4096u

static uint64_t mix64(uint64_t x) {
    x ^= x >> 33; x *= 0xFF51AFD7ED558CCDULL;
    x ^= x >> 33; x *= 0xC4CEB9FE1A85EC53ULL;
    x ^= x >> 33;
    return x;
}

/* baseline memo: same direct-mapped geometry as the engine's */
static uint64_t bl_key[NTAGS][MEMO], bl_val[NTAGS][MEMO];
static uint8_t bl_used[NTAGS][MEMO];

static uint64_t *g_out;
static uint32_t g_n;

static void run_bl_switch(const nmo_record *r) {
    for (uint32_t i = 0; i < g_n; i++)
        g_out[i] = dispatch(r[i].tag, r[i].val);
}

static void run_bl_memo(const nmo_record *r) {
    for (uint32_t i = 0; i < g_n; i++) {
        uint32_t t = r[i].tag;
        uint64_t v = r[i].val;
        uint32_t s = (uint32_t)(mix64(v) & (MEMO - 1));
        if (bl_used[t][s] && bl_key[t][s] == v) {
            g_out[i] = bl_val[t][s];
        } else {
            uint64_t o = dispatch(t, v);
            bl_used[t][s] = 1; bl_key[t][s] = v; bl_val[t][s] = o;
            g_out[i] = o;
        }
    }
}

/* each pass feeds exactly g_n records, so src - pass_base is the
 * stream position; no division on the hot path */
typedef struct { uint64_t base; } sctx_t;
static void sink(void *ctx, const nmo_exit *ex, size_t n) {
    sctx_t *s = ctx;
    for (size_t i = 0; i < n; i++)
        g_out[(uint32_t)(ex[i].src - s->base)] = ex[i].val;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <records.bin> <reps>\n", argv[0]);
        return 1;
    }
    int reps = atoi(argv[2]);

    cpu_set_t set;
    CPU_ZERO(&set); CPU_SET(0, &set);
    sched_setaffinity(0, sizeof(set), &set);

    FILE *f = fopen(argv[1], "rb");
    if (!f) return 1;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    g_n = (uint32_t)(sz / sizeof(nmo_record));
    nmo_record *recs = malloc((size_t)g_n * sizeof(nmo_record));
    if (fread(recs, sizeof(nmo_record), g_n, f) != g_n) return 1;
    fclose(f);

    g_out = malloc((size_t)g_n * 8);
    uint64_t *ref = malloc((size_t)g_n * 8);

    /* engines: plan+memo, jit+memo, jit no-memo */
    struct { const char *name; int jit; uint32_t memo; nmo_engine *e;
             sctx_t sc; }
    engines[3] = {
        { "eng_plan",   0, MEMO, 0, {0} },
        { "eng_jit",    1, MEMO, 0, {0} },
        { "eng_jit_nm", 1, 0,    0, {0} },
    };
    for (int j = 0; j < 3; j++) {
        nmo_config cfg = {
            .max_tags = NTAGS, .batch = 256,
            .memo_entries = engines[j].memo, .jit = engines[j].jit,
            .jit_dir = getenv("NMO_JIT_DIR"), .sink = sink,
            .sink_ctx = &engines[j].sc,
        };
        engines[j].e = nmo_create(&cfg);
        if (!engines[j].e) return 2;
        for (uint32_t t = 0; t < NTAGS; t++) {
            nmo_arrangement a;
            build_arrangement(t, &a);
            if (nmo_plant(engines[j].e, &a) != 0) return 2;
        }
    }

    /* warmup + parity: reference from the idiomatic baseline */
    run_bl_switch(recs);
    memcpy(ref, g_out, (size_t)g_n * 8);
    memset(g_out, 0, (size_t)g_n * 8);
    run_bl_memo(recs);
    if (memcmp(ref, g_out, (size_t)g_n * 8)) {
        fprintf(stderr, "PARITY VIOLATION bl_memo\n"); return 3;
    }
    for (int j = 0; j < 3; j++) {
        double t0 = now_ns();
        memset(g_out, 0, (size_t)g_n * 8);
        nmo_feed(engines[j].e, recs, g_n);
        nmo_drain(engines[j].e);
        engines[j].sc.base += g_n;
        double t1 = now_ns();
        if (memcmp(ref, g_out, (size_t)g_n * 8)) {
            fprintf(stderr, "PARITY VIOLATION %s\n", engines[j].name);
            return 3;
        }
        nmo_stats st;
        nmo_get_stats(engines[j].e, &st);
        /* cold pass: includes all paving; reported, never averaged in */
        printf("{\"variant\":\"%s\",\"rep\":-1,\"cold\":true,"
               "\"ns_per_elem\":%.4f,\"paving_ms\":%.1f,"
               "\"jit_roads\":%llu}\n",
               engines[j].name, (t1 - t0) / g_n, st.paving_ns / 1e6,
               (unsigned long long)st.jit_roads);
    }

    struct { const char *name; int kind; int idx; } variants[5] = {
        { "bl_switch", 0, 0 }, { "bl_memo", 1, 0 },
        { "eng_plan", 2, 0 }, { "eng_jit", 2, 1 }, { "eng_jit_nm", 2, 2 },
    };
    for (int rep = 0; rep < reps; rep++) {
        for (int v = 0; v < 5; v++) {
            double t0 = now_ns();
            if (variants[v].kind == 0) run_bl_switch(recs);
            else if (variants[v].kind == 1) run_bl_memo(recs);
            else {
                nmo_feed(engines[variants[v].idx].e, recs, g_n);
                nmo_drain(engines[variants[v].idx].e);
                engines[variants[v].idx].sc.base += g_n;
            }
            double t1 = now_ns();
            printf("{\"variant\":\"%s\",\"rep\":%d,"
                   "\"ns_per_elem\":%.4f}\n",
                   variants[v].name, rep, (t1 - t0) / g_n);
        }
    }

    for (int j = 0; j < 3; j++) {
        nmo_stats st;
        nmo_get_stats(engines[j].e, &st);
        fprintf(stderr,
                "%s: memo_hits=%llu misses=%llu fired=%llu "
                "network_bytes=%llu\n",
                engines[j].name,
                (unsigned long long)st.memo_hits,
                (unsigned long long)st.memo_misses,
                (unsigned long long)st.fired_elems,
                (unsigned long long)st.resident_network_bytes);
        nmo_destroy(engines[j].e);
    }
    free(recs); free(g_out); free(ref);
    return 0;
}
