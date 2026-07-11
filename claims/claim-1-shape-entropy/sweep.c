/* claim-1 harness: tag-routed dispatch vs branchy dispatch over the
 * same interleaved stream, at one compiled-in shape count NSHAPES.
 *
 * Four variants, identical computation, identical output array:
 *   branchy_switch - dense switch (gcc: jump table = 1 indirect branch
 *                    per element). The strong conventional baseline.
 *   branchy_chain  - binary comparison tree (~log2 N cond. branches).
 *   routed_direct  - per-element hop through the road table
 *                    (SHAPE_FN[tag]). The naive reading of routing.
 *   routed_staged  - the machine's reading: per block, data is
 *                    partitioned by tag into per-road queues held in
 *                    cache (layer 3: "store the queue instead"), then
 *                    each road's pre-staged straight-line plan fires
 *                    over its whole batch (layers 1/4). No per-element
 *                    unpredictable branch exists anywhere on the path.
 *
 * Guarantee parity: every variant writes out[i] = f_tag(i)(val(i)) for
 * every i, and checksums must match exactly or the run aborts.
 * Reordering execution inside a block trades per-element latency for
 * throughput; results land at original indices.
 *
 * Metrics per (variant, rep): wall ns/elem, and - where the PMU is
 * exposed - branch misses/elem and instructions/elem via
 * perf_event_open (both accountings, claim discipline).
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sched.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>

typedef struct { uint64_t val; uint32_t idx; uint32_t pad; } rec_t;

#include "shapes.h"

#define BLOCK 65536u

/* ---- deterministic stream ---- */
static uint64_t rng_state;
static uint64_t rng_next(void) {
    uint64_t x = rng_state;
    x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
    rng_state = x;
    return x * 0x2545F4914F6CDD1DULL;
}

/* ---- perf counters (degrade to -1 if unavailable) ---- */
static long perf_open(uint64_t type, uint64_t config) {
    struct perf_event_attr a;
    memset(&a, 0, sizeof(a));
    a.type = type; a.size = sizeof(a); a.config = config;
    a.disabled = 1; a.exclude_kernel = 1; a.exclude_hv = 1;
    return syscall(SYS_perf_event_open, &a, 0, -1, -1, 0);
}
static long fd_brmiss = -1, fd_instr = -1;
static void perf_init(void) {
    fd_brmiss = perf_open(PERF_TYPE_HARDWARE, PERF_COUNT_HW_BRANCH_MISSES);
    fd_instr  = perf_open(PERF_TYPE_HARDWARE, PERF_COUNT_HW_INSTRUCTIONS);
}
static void perf_start(void) {
    if (fd_brmiss >= 0) { ioctl(fd_brmiss, PERF_EVENT_IOC_RESET, 0);
                          ioctl(fd_brmiss, PERF_EVENT_IOC_ENABLE, 0); }
    if (fd_instr >= 0)  { ioctl(fd_instr, PERF_EVENT_IOC_RESET, 0);
                          ioctl(fd_instr, PERF_EVENT_IOC_ENABLE, 0); }
}
static void perf_stop(int64_t *brmiss, int64_t *instr) {
    *brmiss = -1; *instr = -1;
    if (fd_brmiss >= 0) { ioctl(fd_brmiss, PERF_EVENT_IOC_DISABLE, 0);
        uint64_t v; if (read(fd_brmiss, &v, 8) == 8) *brmiss = (int64_t)v; }
    if (fd_instr >= 0)  { ioctl(fd_instr, PERF_EVENT_IOC_DISABLE, 0);
        uint64_t v; if (read(fd_instr, &v, 8) == 8) *instr = (int64_t)v; }
}

static double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e9 + ts.tv_nsec;
}

/* ---- variants ---- */
static uint32_t *g_tags;
static uint64_t *g_vals, *g_out;
static uint32_t g_m;
static rec_t *g_part;

static void run_branchy_switch(void) {
    for (uint32_t i = 0; i < g_m; i++)
        g_out[i] = dispatch_switch(g_tags[i], g_vals[i]);
}
static void run_branchy_chain(void) {
    for (uint32_t i = 0; i < g_m; i++)
        g_out[i] = dispatch_chain(g_tags[i], g_vals[i]);
}
static void run_routed_direct(void) {
    for (uint32_t i = 0; i < g_m; i++)
        g_out[i] = SHAPE_FN[g_tags[i]](g_vals[i]);
}
static void run_routed_staged(void) {
    uint32_t counts[NSHAPES], offs[NSHAPES], cur[NSHAPES];
    for (uint32_t s = 0; s < g_m; s += BLOCK) {
        uint32_t e = s + BLOCK < g_m ? s + BLOCK : g_m;
        memset(counts, 0, sizeof(counts));
        for (uint32_t i = s; i < e; i++)
            counts[g_tags[i]]++;
        uint32_t acc = 0;
        for (uint32_t k = 0; k < NSHAPES; k++) {
            offs[k] = cur[k] = acc;
            acc += counts[k];
        }
        for (uint32_t i = s; i < e; i++) {
            uint32_t t = g_tags[i], p = cur[t]++;
            g_part[p].val = g_vals[i];
            g_part[p].idx = i;
        }
        for (uint32_t k = 0; k < NSHAPES; k++)
            if (counts[k])
                SHAPE_BATCH[k](g_part + offs[k], counts[k], g_out);
    }
}

static uint64_t checksum_out(void) {
    uint64_t h = 0x243F6A8885A308D3ULL;
    for (uint32_t i = 0; i < g_m; i++)
        h = (h ^ g_out[i]) * 0x9E3779B97F4A7C15ULL;
    return h;
}

typedef struct { const char *name; void (*fn)(void); } variant_t;

int main(int argc, char **argv) {
    if (argc < 5) {
        fprintf(stderr,
            "usage: %s <M> <reps> <uniform|skew> <label>\n", argv[0]);
        return 1;
    }
    g_m = (uint32_t)strtoul(argv[1], 0, 10);
    int reps = atoi(argv[2]);
    int skew = strcmp(argv[3], "skew") == 0;
    const char *label = argv[4];

    cpu_set_t set;
    CPU_ZERO(&set); CPU_SET(0, &set);
    sched_setaffinity(0, sizeof(set), &set);

    g_tags = malloc(g_m * 4);
    g_vals = malloc(g_m * 8);
    g_out  = malloc(g_m * 8);
    g_part = malloc((size_t)BLOCK * sizeof(rec_t));
    if (!g_tags || !g_vals || !g_out || !g_part) return 1;

    rng_state = 0x00C1A1400DBA5E5ULL ^ (NSHAPES * 2654435761u);
    for (uint32_t i = 0; i < g_m; i++) {
        uint64_t r = rng_next();
        if (skew)
            g_tags[i] = (r % 100) < 99
                ? 0 : (uint32_t)((rng_next() * (__uint128_t)NSHAPES) >> 64);
        else
            g_tags[i] = (uint32_t)((r * (__uint128_t)NSHAPES) >> 64);
        g_vals[i] = rng_next();
    }

    perf_init();

    variant_t variants[] = {
        {"branchy_switch", run_branchy_switch},
        {"branchy_chain",  run_branchy_chain},
        {"routed_direct",  run_routed_direct},
        {"routed_staged",  run_routed_staged},
    };
    int nv = 4;

    /* warmup + guarantee-parity check */
    uint64_t ref = 0;
    for (int v = 0; v < nv; v++) {
        variants[v].fn();
        uint64_t h = checksum_out();
        if (v == 0) ref = h;
        else if (h != ref) {
            fprintf(stderr, "PARITY VIOLATION: %s checksum %016lx != %016lx\n",
                    variants[v].name, h, ref);
            return 2;
        }
        memset(g_out, 0, g_m * 8);
    }

    for (int rep = 0; rep < reps; rep++) {
        for (int v = 0; v < nv; v++) {
            int64_t brmiss, instr;
            perf_start();
            double t0 = now_ns();
            variants[v].fn();
            double t1 = now_ns();
            perf_stop(&brmiss, &instr);
            printf("{\"label\":\"%s\",\"nshapes\":%u,\"ops\":%d,"
                   "\"dist\":\"%s\",\"variant\":\"%s\",\"rep\":%d,"
                   "\"ns_per_elem\":%.4f,\"brmiss_per_elem\":%.6f,"
                   "\"instr_per_elem\":%.4f,\"checksum\":\"%016lx\"}\n",
                   label, NSHAPES, SHAPE_OPS, argv[3], variants[v].name,
                   rep, (t1 - t0) / g_m,
                   brmiss < 0 ? -1.0 : (double)brmiss / g_m,
                   instr < 0 ? -1.0 : (double)instr / g_m,
                   checksum_out());
        }
    }
    return 0;
}
