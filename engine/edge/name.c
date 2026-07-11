/* Identity at birth: interning by content happens exactly once, here.
 * Past this point everything is a dense name. */
#include "edge.h"
#include <stdlib.h>

struct nmo_namer {
    uint64_t *key;
    uint32_t *id;
    uint8_t *used;
    uint32_t cap, n;
};

static uint64_t mix64(uint64_t x) {
    x ^= x >> 33; x *= 0xFF51AFD7ED558CCDULL;
    x ^= x >> 33; x *= 0xC4CEB9FE1A85EC53ULL;
    x ^= x >> 33;
    return x;
}

nmo_namer *nmo_namer_new(void) {
    nmo_namer *n = calloc(1, sizeof(*n));
    n->cap = 1u << 16;
    n->key = malloc((size_t)n->cap * 8);
    n->id = malloc((size_t)n->cap * 4);
    n->used = calloc(n->cap, 1);
    return n;
}

void nmo_namer_del(nmo_namer *n) {
    if (!n) return;
    free(n->key); free(n->id); free(n->used); free(n);
}

static void grow(nmo_namer *n) {
    uint32_t nc = n->cap * 2;
    uint64_t *k = malloc((size_t)nc * 8);
    uint32_t *i2 = malloc((size_t)nc * 4);
    uint8_t *u = calloc(nc, 1);
    for (uint32_t i = 0; i < n->cap; i++) {
        if (!n->used[i]) continue;
        uint32_t s = (uint32_t)(mix64(n->key[i]) & (nc - 1));
        while (u[s]) s = (s + 1) & (nc - 1);
        u[s] = 1; k[s] = n->key[i]; i2[s] = n->id[i];
    }
    free(n->key); free(n->id); free(n->used);
    n->key = k; n->id = i2; n->used = u; n->cap = nc;
}

uint32_t nmo_name(nmo_namer *n, uint64_t val, int *novel) {
    if (n->n > n->cap - (n->cap >> 2)) grow(n);
    uint32_t s = (uint32_t)(mix64(val) & (n->cap - 1));
    while (n->used[s]) {
        if (n->key[s] == val) { if (novel) *novel = 0; return n->id[s]; }
        s = (s + 1) & (n->cap - 1);
    }
    n->used[s] = 1; n->key[s] = val; n->id[s] = n->n;
    if (novel) *novel = 1;
    return n->n++;
}

uint32_t nmo_name_count(const nmo_namer *n) { return n->n; }
