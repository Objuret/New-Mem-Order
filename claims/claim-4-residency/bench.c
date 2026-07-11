/* Claim 4 - arrangement-residency fits.
 *
 * Plant a ~1000-shape road network in the engine and let the engine
 * account for its own residency (resident_network_bytes: arrangements
 * + paved plans - the road network itself, exactly what must stay hot).
 * The comparison object, built by run.sh, is the equivalent branchy
 * dispatcher: the claim-1 generator's 1024 shapes inlined into one
 * switch, compiled -O2, .text section sized. Both numbers are
 * measured, neither is narrated.
 *
 * The claim's second half - "where equivalent branchy code plus
 * predictor state cannot [fit]" - includes predictor/BTB state, which
 * no software can measure. verdict.py scores only the measurable
 * halves and says so.
 */
#include "../../engine/nmo.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t rs = 0x00C1A1400DBA5E5ULL;
static uint64_t rnd(void) {
    rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27;
    return rs * 0x2545F4914F6CDD1DULL;
}

int main(int argc, char **argv) {
    uint32_t nroads = argc > 1 ? (uint32_t)strtoul(argv[1], 0, 10) : 1024;
    int ops_per_shape = argc > 2 ? atoi(argv[2]) : 8;

    nmo_config cfg = { .max_tags = nroads, .batch = 256,
                       .memo_entries = 0 };
    nmo_engine *e = nmo_create(&cfg);
    if (!e) return 1;

    /* shapes of the same scale as claim 1's: ~8 ops each, mixed */
    static const uint8_t mix[4] = { NMO_OP_ADD, NMO_OP_XOR,
                                    NMO_OP_MUL, NMO_OP_ROTL };
    for (uint32_t t = 0; t < nroads; t++) {
        nmo_arrangement a;
        memset(&a, 0, sizeof(a));
        a.tag = t;
        a.nodes[0].op = NMO_OP_INPUT;
        uint16_t n = 1, prev = 0;
        for (int d = 0; d < ops_per_shape; d++) {
            uint8_t op = mix[rnd() % 4];
            a.nodes[n].op = NMO_OP_CONST;
            a.nodes[n].imm = (op == NMO_OP_ROTL) ? (rnd() % 63) + 1
                             : (op == NMO_OP_MUL) ? (rnd() | 1) : rnd();
            n++;
            a.nodes[n].op = op;
            a.nodes[n].a = prev;
            a.nodes[n].b = (uint16_t)(n - 1);
            prev = n++;
        }
        a.nnodes = n; a.nexits = 1; a.exits[0] = prev;
        if (nmo_plant(e, &a) != 0) return 2;
        /* arrival = paving: one record per road paves it */
        nmo_record r = { .tag = t, .pad = 0, .val = rnd() };
        nmo_feed(e, &r, 1);
    }
    nmo_drain(e);

    nmo_stats st;
    nmo_get_stats(e, &st);
    printf("{\"roads\":%u,\"ops_per_shape\":%d,"
           "\"network_bytes\":%llu,\"state_bytes\":%llu,"
           "\"bytes_per_road\":%.1f}\n",
           nroads, ops_per_shape,
           (unsigned long long)st.resident_network_bytes,
           (unsigned long long)st.resident_state_bytes,
           (double)st.resident_network_bytes / nroads);
    nmo_destroy(e);
    return 0;
}
