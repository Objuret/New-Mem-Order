/* Claim 2 - circulation beats program-mediated stepping.
 *
 * Same arrangement, same stream, three executions inside one engine:
 *   walker - one operation at a time, intermediates materialized at
 *            every node, control returning to the interpreter loop
 *            between steps (the program-in-the-loop ceremony).
 *   plan   - circulation: the whole road fires over a staged batch;
 *            intermediates live in the road's register file and die
 *            at slot reuse.
 *   jit    - circulation through the jit-paved road: real straight-
 *            line machine code, intermediates in CPU registers. This
 *            doubles as the compiled-ahead reference point.
 *
 * Sweep: tree depth D (number of ops). Predicted sign: circulation's
 * advantage grows with depth as per-step ceremony amortizes away.
 * Result matrix disabled - layer 5 must not contaminate a layer 4
 * measurement. Wall-time accounting only on this host (no PMU;
 * instructions and joules are named by the claim but unmeasurable
 * here - stated, not fudged).
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

static uint64_t rs = 0x00C1A1400DBA5E5ULL;
static uint64_t rnd(void) {
    rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27;
    return rs * 0x2545F4914F6CDD1DULL;
}

/* depth-D chain: v_i = op(v_{i-1}, const_i), ops cycling through a
 * fixed mix; 2D+1 nodes, one exit */
static void make_chain(nmo_arrangement *a, uint32_t tag, int depth) {
    memset(a, 0, sizeof(*a));
    a->tag = tag;
    a->nodes[0].op = NMO_OP_INPUT;
    uint16_t n = 1, prev = 0;
    static const uint8_t mix[4] = { NMO_OP_ADD, NMO_OP_XOR,
                                    NMO_OP_MUL, NMO_OP_ROTL };
    for (int d = 0; d < depth; d++) {
        a->nodes[n].op = NMO_OP_CONST;
        a->nodes[n].imm = (mix[d % 4] == NMO_OP_ROTL) ? (rnd() % 63) + 1
                          : (mix[d % 4] == NMO_OP_MUL) ? (rnd() | 1)
                          : rnd();
        n++;
        a->nodes[n].op = mix[d % 4];
        a->nodes[n].a = prev;
        a->nodes[n].b = (uint16_t)(n - 1);
        prev = n++;
    }
    a->nnodes = n;
    a->nexits = 1;
    a->exits[0] = prev;
}

static uint64_t sink_xor;
static uint64_t sink_count;
static void sink(void *ctx, const nmo_exit *ex, size_t n) {
    (void)ctx;
    for (size_t i = 0; i < n; i++) sink_xor ^= ex[i].val;
    sink_count += n;
}

int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: %s <depth> <M> <reps>\n", argv[0]);
        return 1;
    }
    int depth = atoi(argv[1]);
    uint32_t M = (uint32_t)strtoul(argv[2], 0, 10);
    int reps = atoi(argv[3]);

    cpu_set_t set;
    CPU_ZERO(&set); CPU_SET(0, &set);
    sched_setaffinity(0, sizeof(set), &set);

    nmo_arrangement arr;
    rs = 0x00C1A1400DBA5E5ULL ^ (uint64_t)depth;
    make_chain(&arr, 0, depth);

    nmo_record *recs = malloc((size_t)M * sizeof(*recs));
    for (uint32_t i = 0; i < M; i++) {
        recs[i].tag = 0; recs[i].pad = 0; recs[i].val = rnd();
    }

    /* one engine per mode so jit paving can't leak into plan timing */
    nmo_engine *eng[2];
    for (int j = 0; j < 2; j++) {
        nmo_config cfg = {
            .max_tags = 1, .batch = 256, .memo_entries = 0,
            .jit = j, .jit_dir = getenv("NMO_JIT_DIR"),
            .sink = sink, .sink_ctx = 0,
        };
        eng[j] = nmo_create(&cfg);
        if (!eng[j] || nmo_plant(eng[j], &arr) != 0) return 2;
        /* warmup: pave (arrival = paving) and warm caches */
        sink_xor = 0; sink_count = 0;
        nmo_feed(eng[j], recs, M < 100000 ? M : 100000);
        nmo_drain(eng[j]);
    }

    /* parity across all three modes before timing anything */
    uint64_t want_xor = 0;
    for (uint32_t i = 0; i < M; i++) {
        uint64_t out[1];
        nmo_walk(eng[0], 0, recs[i].val, out);
        want_xor ^= out[0];
    }
    for (int j = 0; j < 2; j++) {
        sink_xor = 0; sink_count = 0;
        nmo_feed(eng[j], recs, M);
        nmo_drain(eng[j]);
        if (sink_xor != want_xor || sink_count != M) {
            fprintf(stderr, "PARITY VIOLATION mode %d\n", j);
            return 3;
        }
    }

    for (int rep = 0; rep < reps; rep++) {
        /* walker: program-mediated stepping */
        uint64_t xsum = 0, out[1];
        double t0 = now_ns();
        for (uint32_t i = 0; i < M; i++) {
            nmo_walk(eng[0], 0, recs[i].val, out);
            xsum ^= out[0];
        }
        double t1 = now_ns();
        if (xsum != want_xor) return 3;
        printf("{\"depth\":%d,\"variant\":\"walker\",\"rep\":%d,"
               "\"ns_per_elem\":%.4f}\n", depth, rep, (t1 - t0) / M);

        static const char *names[2] = { "plan", "jit" };
        for (int j = 0; j < 2; j++) {
            sink_xor = 0; sink_count = 0;
            t0 = now_ns();
            nmo_feed(eng[j], recs, M);
            nmo_drain(eng[j]);
            t1 = now_ns();
            if (sink_xor != want_xor) return 3;
            printf("{\"depth\":%d,\"variant\":\"%s\",\"rep\":%d,"
                   "\"ns_per_elem\":%.4f}\n",
                   depth, names[j], rep, (t1 - t0) / M);
        }
    }

    nmo_stats st;
    nmo_get_stats(eng[1], &st);
    fprintf(stderr, "depth=%d paving_ns_total=%llu jit=%llu\n", depth,
            (unsigned long long)st.paving_ns,
            (unsigned long long)st.jit_roads);
    nmo_destroy(eng[0]);
    nmo_destroy(eng[1]);
    free(recs);
    return 0;
}
