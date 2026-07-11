/* Two ledgers, always: machine_account (inside the fabric) and
 * emulation_account (the edge shell), never blended.
 * Gate asserts live here:
 *   LAW_G1_DISPATCH_BUDGET - nmo_arrive instruction count (objdump,
 *                            build-time) <= stated constant
 *   LAW_G2_EXIT_BYTES      - wire record = name+value, <= 12 bytes
 *   LAW_G4_NOALLOC         - zero heap movement across the arrive loop
 */
#define _GNU_SOURCE
#include "../edge/edge.h"
#include "g1_count.h"
#include <malloc.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define LAW_G1_DISPATCH_BUDGET 40
_Static_assert(G1_DISPATCH_INSTRUCTIONS <= LAW_G1_DISPATCH_BUDGET,
               "G1: nmo_arrive exceeds the stated instruction budget");

static double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e9 + ts.tv_nsec;
}

static uint64_t rs = 0xC1A140;
static uint64_t rnd(void) {
    rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27;
    return rs * 0x2545F4914F6CDD1DULL;
}

/* per-tag enrichment kernel, same species as niche #1 */
static void kernel(nmo_tree *t, uint32_t tag) {
    memset(t, 0, sizeof(*t));
    t->tag = tag;
    rs = 0xC1A140 ^ tag;
    uint16_t n = 0;
    t->nodes[n++].op = NMO_OP_INPUT;
#define K(o, A, B, IMM) do { t->nodes[n].op = (o); t->nodes[n].a = (A); \
    t->nodes[n].b = (B); t->nodes[n].imm = (IMM); n++; } while (0)
    K(NMO_OP_CONST, 0, 0, 0xFFFFFFFFFFFFF000ULL);
    K(NMO_OP_LT, 1, 0, 0);                        /* 2: errno fork  */
    K(NMO_OP_CONST, 0, 0, rnd() % 9 + 3);
    K(NMO_OP_SHR, 0, 3, 0);                       /* 4: size class  */
    K(NMO_OP_CONST, 0, 0, rnd() | 1);
    K(NMO_OP_MUL, 0, 5, 0);                       /* 6: mix         */
    int reps = (int)(rnd() % 3) + 1;
    uint16_t m = 6;
    for (int i = 0; i < reps; i++) {
        K(NMO_OP_CONST, 0, 0, rnd());
        K(NMO_OP_XOR, m, n - 1, 0);
        K(NMO_OP_CONST, 0, 0, rnd() % 62 + 1);
        K(NMO_OP_ROTL, n - 2, n - 1, 0);
        m = n - 1;
    }
    K(NMO_OP_ADD, m, 4, 0);
    uint16_t norm = n - 1;
    K(NMO_OP_CONST, 0, 0, rnd() | (tag + 1));
    K(NMO_OP_XOR, 0, n - 1, 0);
    uint16_t err = n - 1;
    t->nodes[n].op = NMO_OP_SELECT;
    t->nodes[n].a = 2; t->nodes[n].b = err; t->nodes[n].c = norm;
    n++;
#undef K
    t->nnodes = n;
    t->nexits = 1;
    t->exits[0] = n - 1;
    t->exit_to[0] = NMO_EXIT_BOUNDARY;
}

int main(int argc, char **argv) {
    const char *trace_dir = argc > 1 ? argv[1] : "traces";
    int reps = argc > 2 ? atoi(argv[2]) : 9;

    cpu_set_t set;
    CPU_ZERO(&set); CPU_SET(0, &set);
    sched_setaffinity(0, sizeof(set), &set);

    /* ---- emulation_account: the edge converts, once ---- */
    nmo_namer *nm = nmo_namer_new();
    nmo_stream s;
    double t0 = now_ns();
    if (nmo_convert_strace(trace_dir, nm, &s) != 0) {
        fprintf(stderr, "no traces in %s\n", trace_dir);
        return 1;
    }
    double convert_ns = (now_ns() - t0) / (double)s.n;

    nmo_tree *trees = malloc((size_t)s.ntags * sizeof(nmo_tree));
    for (uint32_t t = 0; t < s.ntags; t++) kernel(&trees[t], t);

    uint64_t *exits = malloc((size_t)(s.n + 8) * 8);
    struct cfg { const char *name; int pave; uint32_t span; };
    struct cfg cfgs[3] = {
        { "walker", 0, 0 },
        { "paved", 1, 0 },
        { "paved+matrix", 1, s.name_span },
    };

    uint64_t *ref = 0;
    size_t refn = 0;
    double paving_ms = 0, mean[3], lo[3], hi[3];
    for (int k = 0; k < 3; k++) {
        nmo_fabric *f = nmo_plant(trees, s.ntags, s.ntags,
                                  cfgs[k].span, exits);
        if (!f) return 2;
        if (cfgs[k].pave) {
            double p0 = now_ns();
            if (nmo_pave_all(f, getenv("NMO_JIT_DIR"), 0) != 0)
                return 2;
            if (k == 1) paving_ms = (now_ns() - p0) / 1e6;
        }
        /* warmup + parity */
        f->exit_at = exits;
        for (size_t i = 0; i < s.n; i++)
            nmo_arrive_inl(f, s.arr[i].tag, s.arr[i].name, s.arr[i].val);
        size_t nex = (size_t)(f->exit_at - exits);
        if (k == 0) {
            ref = malloc(nex * 8);
            memcpy(ref, exits, nex * 8);
            refn = nex;
        } else if (nex != refn || memcmp(ref, exits, refn * 8)) {
            fprintf(stderr, "PARITY VIOLATION %s\n", cfgs[k].name);
            return 3;
        }

        /* LAW_G4_NOALLOC: heap must not move across the arrive loop */
        struct mallinfo2 mi0 = mallinfo2();
        double best = 1e18, worst = 0, sum = 0;
        for (int rep = 0; rep < reps; rep++) {
            f->exit_at = exits;
            double a0 = now_ns();
            for (size_t i = 0; i < s.n; i++)
                nmo_arrive_inl(f, s.arr[i].tag, s.arr[i].name, s.arr[i].val);
            double d = (now_ns() - a0) / (double)s.n;
            if (d < best) best = d;
            if (d > worst) worst = d;
            sum += d;
        }
        struct mallinfo2 mi1 = mallinfo2();
        if (mi0.uordblks != mi1.uordblks) {
            fprintf(stderr, "G4 VIOLATION: heap moved in arrive loop\n");
            return 4;
        }
        mean[k] = sum / reps; lo[k] = best; hi[k] = worst;
        nmo_unplant(f);
    }

    printf("{\"stream\":{\"events\":%zu,\"tags\":%u,"
           "\"entropy_before\":%.3f,\"entropy_after\":%.3f,"
           "\"name_span\":%u},\n", s.n, s.ntags,
           s.entropy_before, s.entropy_after, s.name_span);
    printf(" \"emulation_account\":{\"convert_ns_per_event\":%.2f,"
           "\"paving_ms\":%.1f},\n", convert_ns, paving_ms);
    printf(" \"machine_account\":[");
    for (int k = 0; k < 3; k++)
        printf("%s{\"cfg\":\"%s\",\"ns_per_event\":"
               "{\"mean\":%.2f,\"min\":%.2f,\"max\":%.2f}}",
               k ? "," : "", cfgs[k].name, mean[k], lo[k], hi[k]);
    printf("],\n");

    /* LAW_G2_EXIT_BYTES: wire record = name+value <= 12B, ref 4B */
    nmo_chan *c = nmo_chan_new(nm);
    nmo_chan_send(c, ref, refn);
    uint64_t wire = nmo_chan_bytes(c);
    if (wire > refn * 12) {
        fprintf(stderr, "G2 VIOLATION: >12B per exit on the wire\n");
        return 5;
    }
    printf(" \"boundary\":{\"exits\":%zu,\"wire_bytes\":%llu,"
           "\"bytes_per_exit\":%.2f},\n", refn,
           (unsigned long long)wire, (double)wire / refn);
    printf(" \"g1_dispatch_instructions\":%d}\n",
           G1_DISPATCH_INSTRUCTIONS);
    nmo_chan_del(c);
    nmo_namer_del(nm);
    return 0;
}
