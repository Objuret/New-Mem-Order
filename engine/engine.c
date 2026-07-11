/* THE ENGINE - core.
 *
 * Layer map (MACHINE.md):
 *   L1 roads       - pave(): every planted shape becomes a pre-staged
 *                    straight-line plan (or real machine code via jit);
 *                    novel shapes are paved on first arrival.
 *   L2 tags        - nmo_feed(): the tag is a direct index into the
 *                    road table; routing never inspects the payload.
 *                    Value-forks exist only as NMO_OP_SELECT inside
 *                    arrangements - honest, small, never eliminable.
 *   L3 residency   - the vocabulary is compiled in (installed once);
 *                    a road adds only arrangement: nodes + plan steps,
 *                    tens of bytes per op. Queues live with the road.
 *   L4 circulation - fire_road(): the whole plan fires over a staged
 *                    batch; intermediates live in the road's register
 *                    file (or actual CPU registers on the jit path),
 *                    are never addressable outside, and die at slot
 *                    reuse. Control never returns to a program between
 *                    steps.
 *   L5 exits       - only exit-node values leave a firing; the result
 *                    matrix (per-road memo) turns recurrence into
 *                    lookup; channels turn recurrence into names.
 */
#define _GNU_SOURCE
#include "nmo.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <dlfcn.h>

typedef struct {
    uint8_t op, dst, sa, sb, sc;
    uint64_t imm;
} nmo_step;

typedef void (*nmo_jit_fn)(const uint64_t *in, uint32_t n,
                           uint64_t *const *ex);

typedef struct {
    nmo_arrangement arr;
    /* paved plan */
    int paved;
    nmo_step *steps;
    uint16_t nsteps, nslots;
    uint8_t exit_slot[NMO_MAX_EXITS];
    /* jit road (real straight-line machine code) */
    void *dl;
    nmo_jit_fn jit_fn;
    uint64_t *jit_ex;       /* nexits * batch exit landing zone */
    /* staging queue (L3: the cache stores the queue) */
    uint64_t *qval, *qsrc;
    uint32_t qn;
    /* register file for plan firing */
    uint64_t *regs;
    /* result matrix (L5): direct-mapped, grown by occurrence */
    uint64_t *memo_key, *memo_val;
    uint8_t *memo_used;
} nmo_road;

struct nmo_engine {
    nmo_config cfg;
    nmo_road **roads;
    uint64_t seq;
    nmo_stats st;
    /* global naming: value -> dense name, by carried identity */
    uint64_t *name_key;
    uint32_t *name_id;
    uint8_t *name_used;
    uint32_t name_cap, name_n;
    /* exit delivery buffer */
    nmo_exit *exbuf;
    size_t exn, excap;
};

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}

static uint64_t mix64(uint64_t x) {
    x ^= x >> 33; x *= 0xFF51AFD7ED558CCDULL;
    x ^= x >> 33; x *= 0xC4CEB9FE1A85EC53ULL;
    x ^= x >> 33;
    return x;
}

/* ---------------- vocabulary arity ---------------- */

static int op_arity(uint8_t op) {
    switch (op) {
    case NMO_OP_INPUT: case NMO_OP_CONST: return 0;
    case NMO_OP_SELECT: return 3;
    default: return op < NMO_OP_COUNT ? 2 : -1;
    }
}

/* ---------------- safety condition ----------------
 * Data may only arrange the fixed vocabulary. Everything else is
 * rejected at the door, before anything is installed. */
static int validate(const nmo_arrangement *a) {
    if (a->nnodes == 0 || a->nnodes > NMO_MAX_NODES) return -1;
    if (a->nexits == 0 || a->nexits > NMO_MAX_EXITS) return -2;
    for (uint16_t i = 0; i < a->nnodes; i++) {
        const nmo_node *nd = &a->nodes[i];
        int ar = op_arity(nd->op);
        if (ar < 0) return -3;                    /* not in vocabulary */
        if (ar >= 1 && nd->a >= i) return -4;     /* forward/self ref  */
        if (ar >= 2 && nd->b >= i) return -4;
        if (ar >= 3 && nd->c >= i) return -4;
    }
    for (uint16_t p = 0; p < a->nexits; p++)
        if (a->exits[p] >= a->nnodes) return -5;
    return 0;
}

/* ---------------- the single slow walker (L1) ----------------
 * One operation at a time, intermediates materialized at every node,
 * control returning to this loop between steps: the program-in-the-
 * loop ceremony, kept as the generic road and the claim-2 baseline. */
static void walk_arrangement(const nmo_arrangement *a, uint64_t x,
                             uint64_t *out) {
    uint64_t vals[NMO_MAX_NODES];
    for (uint16_t i = 0; i < a->nnodes; i++) {
        const nmo_node *nd = &a->nodes[i];
        uint64_t v;
        switch (nd->op) {
        case NMO_OP_INPUT: v = x; break;
        case NMO_OP_CONST: v = nd->imm; break;
        case NMO_OP_SELECT:
            v = vals[nd->a] ? vals[nd->b] : vals[nd->c]; break;
#define X(NAME, EXPR) \
        case NMO_OP_##NAME: { \
            uint64_t l = vals[nd->a], r = vals[nd->b]; \
            v = (EXPR); } break;
        NMO_BINOPS(X)
#undef X
        default: v = 0; break;
        }
        vals[i] = v;
    }
    for (uint16_t p = 0; p < a->nexits; p++)
        out[p] = vals[a->exits[p]];
}

int nmo_walk(nmo_engine *e, uint32_t tag, uint64_t val, uint64_t *out) {
    if (tag >= e->cfg.max_tags || !e->roads[tag]) return -1;
    walk_arrangement(&e->roads[tag]->arr, val, out);
    e->st.walker_elems++;
    return (int)e->roads[tag]->arr.nexits;
}

/* ---------------- paving (L1): arrangement -> firing plan ----------
 * Linearize with register liveness: a slot is freed at its holder's
 * last use - intermediates literally die, and peak-live bounds the
 * register file, not node count. */
static void pave_plan(nmo_road *rd) {
    const nmo_arrangement *a = &rd->arr;
    uint16_t last[NMO_MAX_NODES];
    uint8_t slot_of[NMO_MAX_NODES], freed[NMO_MAX_NODES] = {0};
    uint8_t freelist[NMO_MAX_NODES];
    int nfree = 0, nslots = 0;

    for (uint16_t i = 0; i < a->nnodes; i++) last[i] = i;
    for (uint16_t i = 0; i < a->nnodes; i++) {
        int ar = op_arity(a->nodes[i].op);
        if (ar >= 1) last[a->nodes[i].a] = i;
        if (ar >= 2) last[a->nodes[i].b] = i;
        if (ar >= 3) last[a->nodes[i].c] = i;
    }
    for (uint16_t p = 0; p < a->nexits; p++)
        last[a->exits[p]] = 0xFFFF;             /* exits never die */

    rd->steps = malloc(a->nnodes * sizeof(nmo_step));
    rd->nsteps = a->nnodes;
    for (uint16_t i = 0; i < a->nnodes; i++) {
        const nmo_node *nd = &a->nodes[i];
        int ar = op_arity(nd->op);
        nmo_step *s = &rd->steps[i];
        s->op = nd->op; s->imm = nd->imm;
        s->sa = ar >= 1 ? slot_of[nd->a] : 0;
        s->sb = ar >= 2 ? slot_of[nd->b] : 0;
        s->sc = ar >= 3 ? slot_of[nd->c] : 0;
        /* operands whose last use is now die here */
        uint16_t ops3[3] = { nd->a, nd->b, nd->c };
        for (int k = 0; k < ar; k++) {
            uint16_t src = ops3[k];
            if (last[src] == i && !freed[src]) {
                freed[src] = 1;
                freelist[nfree++] = slot_of[src];
            }
        }
        s->dst = nfree ? freelist[--nfree] : (uint8_t)nslots++;
        slot_of[i] = s->dst;
    }
    rd->nslots = (uint16_t)nslots;
    for (uint16_t p = 0; p < a->nexits; p++)
        rd->exit_slot[p] = slot_of[a->exits[p]];
}

/* ---- jit paving: the plan becomes real straight-line machine code,
 * intermediates in actual CPU registers. The generated text is fully
 * determined by the validated arrangement: vetted ops + topology +
 * immediates as operands. Data contributes no code. ---- */
static const char *binop_expr(uint8_t op) {
    switch (op) {
#define X(NAME, EXPR) case NMO_OP_##NAME: return #EXPR;
    NMO_BINOPS(X)
#undef X
    default: return 0;
    }
}

static int pave_jit(nmo_engine *e, nmo_road *rd) {
    const nmo_arrangement *a = &rd->arr;
    char cpath[512], sopath[512], cmd[1200];
    const char *dir = e->cfg.jit_dir ? e->cfg.jit_dir : "/tmp";
    snprintf(cpath, sizeof(cpath), "%s/nmo_road_%u.c", dir, a->tag);
    snprintf(sopath, sizeof(sopath), "%s/nmo_road_%u.so", dir, a->tag);

    FILE *f = fopen(cpath, "w");
    if (!f) return -1;
    fprintf(f, "#include <stdint.h>\n"
               "void nmo_road_fire(const uint64_t *in, uint32_t n,"
               " uint64_t *const *ex) {\n"
               "  for (uint32_t i = 0; i < n; i++) {\n"
               "    uint64_t x = in[i];\n");
    for (uint16_t i = 0; i < a->nnodes; i++) {
        const nmo_node *nd = &a->nodes[i];
        switch (nd->op) {
        case NMO_OP_INPUT:
            fprintf(f, "    uint64_t v%u = x;\n", i); break;
        case NMO_OP_CONST:
            fprintf(f, "    uint64_t v%u = 0x%016llxULL;\n",
                    i, (unsigned long long)nd->imm); break;
        case NMO_OP_SELECT:
            fprintf(f, "    uint64_t v%u = v%u ? v%u : v%u;\n",
                    i, nd->a, nd->b, nd->c); break;
        default:
            fprintf(f, "    uint64_t v%u; { uint64_t l = v%u, r = v%u;"
                       " v%u = (%s); }\n",
                    i, nd->a, nd->b, i, binop_expr(nd->op));
        }
    }
    for (uint16_t p = 0; p < a->nexits; p++)
        fprintf(f, "    ex[%u][i] = v%u;\n", p, a->exits[p]);
    fprintf(f, "  }\n}\n");
    fclose(f);

    snprintf(cmd, sizeof(cmd), "%s -O2 -shared -fPIC -o %s %s 2>/dev/null",
             e->cfg.cc ? e->cfg.cc : "cc", sopath, cpath);
    if (system(cmd) != 0) return -1;
    rd->dl = dlopen(sopath, RTLD_NOW | RTLD_LOCAL);
    if (!rd->dl) return -1;
    rd->jit_fn = (nmo_jit_fn)dlsym(rd->dl, "nmo_road_fire");
    if (!rd->jit_fn) { dlclose(rd->dl); rd->dl = 0; return -1; }
    rd->jit_ex = malloc((size_t)a->nexits * e->cfg.batch * 8);
    return rd->jit_ex ? 0 : -1;
}

static void pave(nmo_engine *e, nmo_road *rd) {
    uint64_t t0 = now_ns();
    pave_plan(rd);
    rd->regs = malloc((size_t)rd->nslots * e->cfg.batch * 8);
    if (e->cfg.jit && pave_jit(e, rd) == 0)
        e->st.jit_roads++;
    rd->paved = 1;
    e->st.paved_roads++;
    e->st.paving_ns += now_ns() - t0;
    e->st.resident_network_bytes +=
        rd->nsteps * sizeof(nmo_step) +
        rd->arr.nnodes * sizeof(nmo_node) + sizeof(uint32_t);
    e->st.resident_state_bytes +=
        (size_t)rd->nslots * e->cfg.batch * 8 +
        (rd->jit_ex ? (size_t)rd->arr.nexits * e->cfg.batch * 8 : 0);
}

/* ---------------- exits delivery ---------------- */

static void flush_exits(nmo_engine *e) {
    if (e->exn && e->cfg.sink)
        e->cfg.sink(e->cfg.sink_ctx, e->exbuf, e->exn);
    e->st.exits_emitted += e->exn;
    e->exn = 0;
}

static inline void emit_exit(nmo_engine *e, uint32_t tag, uint16_t port,
                             uint64_t src, uint64_t val) {
    if (e->exn == e->excap) flush_exits(e);
    nmo_exit *x = &e->exbuf[e->exn++];
    x->tag = tag; x->port = port; x->pad = 0; x->src = src; x->val = val;
}

/* ---------------- circulation (L4): firing a staged batch ---------- */

static void fire_plan(nmo_road *rd, const uint64_t *in, uint32_t n,
                      uint32_t batch) {
    uint64_t *regs = rd->regs;
    for (uint16_t si = 0; si < rd->nsteps; si++) {
        const nmo_step *s = &rd->steps[si];
        uint64_t *Rd = regs + (size_t)s->dst * batch;
        const uint64_t *Ra = regs + (size_t)s->sa * batch;
        const uint64_t *Rb = regs + (size_t)s->sb * batch;
        const uint64_t *Rc = regs + (size_t)s->sc * batch;
        switch (s->op) {
        case NMO_OP_INPUT:
            for (uint32_t i = 0; i < n; i++) Rd[i] = in[i];
            break;
        case NMO_OP_CONST: {
            uint64_t imm = s->imm;
            for (uint32_t i = 0; i < n; i++) Rd[i] = imm;
            break; }
        case NMO_OP_SELECT:
            for (uint32_t i = 0; i < n; i++)
                Rd[i] = Ra[i] ? Rb[i] : Rc[i];
            break;
#define X(NAME, EXPR) \
        case NMO_OP_##NAME: \
            for (uint32_t i = 0; i < n; i++) { \
                uint64_t l = Ra[i], r = Rb[i]; \
                Rd[i] = (EXPR); } \
            break;
        NMO_BINOPS(X)
#undef X
        default: break;
        }
    }
}

static void memo_insert(nmo_engine *e, nmo_road *rd, uint64_t key,
                        const uint64_t *exvals) {
    if (!e->cfg.memo_entries) return;
    uint32_t slot = (uint32_t)(mix64(key) & (e->cfg.memo_entries - 1));
    rd->memo_key[slot] = key;
    rd->memo_used[slot] = 1;
    memcpy(rd->memo_val + (size_t)slot * rd->arr.nexits, exvals,
           rd->arr.nexits * 8);
}

static void fire_road(nmo_engine *e, nmo_road *rd) {
    uint32_t n = rd->qn;
    if (!n) return;
    if (!rd->paved) pave(e, rd);        /* arrival = paving */
    uint32_t tag = rd->arr.tag;
    uint16_t nexits = rd->arr.nexits;
    uint32_t batch = e->cfg.batch;

    if (rd->jit_fn) {
        uint64_t *ex[NMO_MAX_EXITS];
        for (uint16_t p = 0; p < nexits; p++)
            ex[p] = rd->jit_ex + (size_t)p * batch;
        rd->jit_fn(rd->qval, n, ex);
        for (uint32_t i = 0; i < n; i++) {
            uint64_t exvals[NMO_MAX_EXITS];
            for (uint16_t p = 0; p < nexits; p++) {
                exvals[p] = ex[p][i];
                emit_exit(e, tag, p, rd->qsrc[i], exvals[p]);
            }
            memo_insert(e, rd, rd->qval[i], exvals);
        }
    } else {
        fire_plan(rd, rd->qval, n, batch);
        for (uint32_t i = 0; i < n; i++) {
            uint64_t exvals[NMO_MAX_EXITS];
            for (uint16_t p = 0; p < nexits; p++) {
                exvals[p] = rd->regs[(size_t)rd->exit_slot[p] * batch + i];
                emit_exit(e, tag, p, rd->qsrc[i], exvals[p]);
            }
            memo_insert(e, rd, rd->qval[i], exvals);
        }
    }
    e->st.fired_batches++;
    e->st.fired_elems += n;
    rd->qn = 0;
}

/* ---------------- routing (L2): tag -> road, one indexed hop ------- */

size_t nmo_feed(nmo_engine *e, const nmo_record *recs, size_t n) {
    const uint32_t maxt = e->cfg.max_tags;
    const uint32_t me = e->cfg.memo_entries;
    for (size_t i = 0; i < n; i++) {
        uint64_t src = e->seq++;
        uint32_t tag = recs[i].tag;
        e->st.fed++;
        if (tag >= maxt || !e->roads[tag]) { e->st.unrouted++; continue; }
        nmo_road *rd = e->roads[tag];
        e->st.routed++;
        uint64_t v = recs[i].val;
        if (me && rd->paved) {
            /* the result matrix: recurrence rides as lookup */
            uint32_t slot = (uint32_t)(mix64(v) & (me - 1));
            if (rd->memo_used[slot] && rd->memo_key[slot] == v) {
                e->st.memo_hits++;
                const uint64_t *exv =
                    rd->memo_val + (size_t)slot * rd->arr.nexits;
                for (uint16_t p = 0; p < rd->arr.nexits; p++)
                    emit_exit(e, tag, p, src, exv[p]);
                continue;
            }
            e->st.memo_misses++;
        }
        rd->qval[rd->qn] = v;
        rd->qsrc[rd->qn] = src;
        if (++rd->qn == e->cfg.batch)
            fire_road(e, rd);
    }
    flush_exits(e);
    return n;
}

void nmo_drain(nmo_engine *e) {
    for (uint32_t t = 0; t < e->cfg.max_tags; t++)
        if (e->roads[t] && e->roads[t]->qn)
            fire_road(e, e->roads[t]);
    flush_exits(e);
}

/* ---------------- planting ---------------- */

int nmo_plant(nmo_engine *e, const nmo_arrangement *a) {
    int rc = validate(a);
    if (rc) return rc;
    if (a->tag >= e->cfg.max_tags) return -6;
    if (e->roads[a->tag]) return -7;            /* roads are immutable */
    nmo_road *rd = calloc(1, sizeof(*rd));
    if (!rd) return -8;
    rd->arr = *a;
    rd->qval = malloc((size_t)e->cfg.batch * 8);
    rd->qsrc = malloc((size_t)e->cfg.batch * 8);
    if (e->cfg.memo_entries) {
        rd->memo_key = malloc((size_t)e->cfg.memo_entries * 8);
        rd->memo_val = malloc((size_t)e->cfg.memo_entries * a->nexits * 8);
        rd->memo_used = calloc(e->cfg.memo_entries, 1);
        e->st.resident_state_bytes += e->cfg.memo_entries * (9 + a->nexits * 8);
    }
    e->st.resident_state_bytes += (size_t)e->cfg.batch * 16;
    e->roads[a->tag] = rd;
    return 0;
}

/* ---------------- lifecycle ---------------- */

nmo_engine *nmo_create(const nmo_config *cfg) {
    nmo_engine *e = calloc(1, sizeof(*e));
    if (!e) return 0;
    e->cfg = *cfg;
    if (!e->cfg.batch) e->cfg.batch = 256;
    if (e->cfg.memo_entries & (e->cfg.memo_entries - 1)) {
        free(e); return 0;                      /* must be power of 2 */
    }
    e->roads = calloc(e->cfg.max_tags, sizeof(nmo_road *));
    e->excap = 4096;
    e->exbuf = malloc(e->excap * sizeof(nmo_exit));
    e->name_cap = 1u << 16;
    e->name_key = malloc((size_t)e->name_cap * 8);
    e->name_id = malloc((size_t)e->name_cap * 4);
    e->name_used = calloc(e->name_cap, 1);
    if (!e->roads || !e->exbuf || !e->name_key || !e->name_id
        || !e->name_used) { nmo_destroy(e); return 0; }
    return e;
}

void nmo_destroy(nmo_engine *e) {
    if (!e) return;
    for (uint32_t t = 0; e->roads && t < e->cfg.max_tags; t++) {
        nmo_road *rd = e->roads[t];
        if (!rd) continue;
        free(rd->steps); free(rd->qval); free(rd->qsrc); free(rd->regs);
        free(rd->memo_key); free(rd->memo_val); free(rd->memo_used);
        free(rd->jit_ex);
        if (rd->dl) dlclose(rd->dl);
        free(rd);
    }
    free(e->roads); free(e->exbuf);
    free(e->name_key); free(e->name_id); free(e->name_used);
    free(e);
}

void nmo_get_stats(nmo_engine *e, nmo_stats *s) { *s = e->st; }

/* ---------------- naming + channels (L5) ---------------- */

static void name_grow(nmo_engine *e) {
    uint32_t ncap = e->name_cap * 2;
    uint64_t *nk = malloc((size_t)ncap * 8);
    uint32_t *ni = malloc((size_t)ncap * 4);
    uint8_t *nu = calloc(ncap, 1);
    for (uint32_t i = 0; i < e->name_cap; i++) {
        if (!e->name_used[i]) continue;
        uint32_t s = (uint32_t)(mix64(e->name_key[i]) & (ncap - 1));
        while (nu[s]) s = (s + 1) & (ncap - 1);
        nu[s] = 1; nk[s] = e->name_key[i]; ni[s] = e->name_id[i];
    }
    free(e->name_key); free(e->name_id); free(e->name_used);
    e->name_key = nk; e->name_id = ni; e->name_used = nu;
    e->name_cap = ncap;
}

/* first occurrence assigns a name; identity is carried (the value),
 * never computed from content */
static uint32_t name_intern(nmo_engine *e, uint64_t val, int *novel) {
    if (e->name_n > e->name_cap - (e->name_cap >> 2)) name_grow(e);
    uint32_t s = (uint32_t)(mix64(val) & (e->name_cap - 1));
    while (e->name_used[s]) {
        if (e->name_key[s] == val) { *novel = 0; return e->name_id[s]; }
        s = (s + 1) & (e->name_cap - 1);
    }
    e->name_used[s] = 1;
    e->name_key[s] = val;
    e->name_id[s] = ++e->name_n;
    *novel = 1;
    return e->name_n;
}

struct nmo_channel {
    nmo_engine *e;
    uint8_t *held; size_t held_cap;         /* far side holds name? */
    uint8_t *wire; size_t wire_len, wire_cap, rdpos;
    uint64_t bytes;
    uint64_t *rvals; size_t rcap;           /* receiver: name -> value */
};

nmo_channel *nmo_chan_create(nmo_engine *e) {
    nmo_channel *c = calloc(1, sizeof(*c));
    c->e = e;
    c->held_cap = 1u << 16; c->held = calloc(c->held_cap, 1);
    c->rcap = 1u << 16; c->rvals = calloc(c->rcap, 8);
    c->wire_cap = 1u << 20; c->wire = malloc(c->wire_cap);
    return c;
}

void nmo_chan_destroy(nmo_channel *c) {
    if (!c) return;
    free(c->held); free(c->wire); free(c->rvals); free(c);
}

static void chan_put(nmo_channel *c, const void *p, size_t n) {
    if (c->wire_len + n > c->wire_cap) {
        while (c->wire_len + n > c->wire_cap) c->wire_cap *= 2;
        c->wire = realloc(c->wire, c->wire_cap);
    }
    memcpy(c->wire + c->wire_len, p, n);
    c->wire_len += n;
    c->bytes += n;
}

size_t nmo_chan_send(nmo_channel *c, const uint64_t *vals, size_t n) {
    for (size_t i = 0; i < n; i++) {
        int novel;
        uint32_t name = name_intern(c->e, vals[i], &novel);
        if (name >= c->held_cap) {
            size_t nc = c->held_cap;
            while (name >= nc) nc *= 2;
            c->held = realloc(c->held, nc);
            memset(c->held + c->held_cap, 0, nc - c->held_cap);
            c->held_cap = nc;
        }
        if (!c->held[name]) {
            /* value travels once per novelty */
            uint32_t hdr = name | 0x80000000u;
            chan_put(c, &hdr, 4);
            chan_put(c, &vals[i], 8);
            c->held[name] = 1;
        } else {
            /* recurrence travels as reference */
            uint32_t hdr = name;
            chan_put(c, &hdr, 4);
        }
    }
    return n;
}

size_t nmo_chan_decode(nmo_channel *c, uint64_t *vals, size_t cap) {
    size_t out = 0;
    while (out < cap && c->rdpos + 4 <= c->wire_len) {
        uint32_t hdr;
        memcpy(&hdr, c->wire + c->rdpos, 4);
        c->rdpos += 4;
        uint32_t name = hdr & 0x7FFFFFFFu;
        if (name >= c->rcap) {
            size_t nc = c->rcap;
            while (name >= nc) nc *= 2;
            c->rvals = realloc(c->rvals, nc * 8);
            memset(c->rvals + c->rcap, 0, (nc - c->rcap) * 8);
            c->rcap = nc;
        }
        if (hdr & 0x80000000u) {
            memcpy(&c->rvals[name], c->wire + c->rdpos, 8);
            c->rdpos += 8;
        }
        vals[out++] = c->rvals[name];
    }
    return out;
}

uint64_t nmo_chan_bytes_sent(const nmo_channel *c) { return c->bytes; }

void nmo_chan_reset_wire(nmo_channel *c) {
    c->wire_len = 0; c->rdpos = 0; c->bytes = 0;
}
