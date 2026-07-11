/* The wire: a value crosses once (name+value, 12B), recurrence
 * crosses as a 4B name. Exit records carry name + value and nothing
 * else - asserted in the harness (LAW_G2_EXIT_BYTES). */
#include "edge.h"
#include <stdlib.h>
#include <string.h>

struct nmo_chan {
    nmo_namer *nm;
    uint8_t *sent;       /* name -> far side holds it */
    size_t sent_cap;
    uint8_t *wire;
    size_t len, cap, rd;
    uint64_t bytes;
    uint64_t *rv;        /* receiver: name -> value */
    size_t rcap;
};

nmo_chan *nmo_chan_new(nmo_namer *nm) {
    nmo_chan *c = calloc(1, sizeof(*c));
    c->nm = nm;
    c->sent_cap = 1u << 16; c->sent = calloc(c->sent_cap, 1);
    c->rcap = 1u << 16; c->rv = calloc(c->rcap, 8);
    c->cap = 1u << 20; c->wire = malloc(c->cap);
    return c;
}

void nmo_chan_del(nmo_chan *c) {
    if (!c) return;
    free(c->sent); free(c->wire); free(c->rv); free(c);
}

static void put(nmo_chan *c, const void *p, size_t n) {
    if (c->len + n > c->cap) {
        while (c->len + n > c->cap) c->cap *= 2;
        c->wire = realloc(c->wire, c->cap);
    }
    memcpy(c->wire + c->len, p, n);
    c->len += n; c->bytes += n;
}

size_t nmo_chan_send(nmo_chan *c, const uint64_t *vals, size_t n) {
    for (size_t i = 0; i < n; i++) {
        uint32_t name = nmo_name(c->nm, vals[i], 0);
        if (name >= c->sent_cap) {
            size_t nc = c->sent_cap;
            while (name >= nc) nc *= 2;
            c->sent = realloc(c->sent, nc);
            memset(c->sent + c->sent_cap, 0, nc - c->sent_cap);
            c->sent_cap = nc;
        }
        if (!c->sent[name]) {
            uint32_t hdr = name | 0x80000000u;
            put(c, &hdr, 4);
            put(c, &vals[i], 8);
            c->sent[name] = 1;
        } else {
            put(c, &name, 4);
        }
    }
    return n;
}

size_t nmo_chan_recv(nmo_chan *c, uint64_t *vals, size_t cap) {
    size_t out = 0;
    while (out < cap && c->rd + 4 <= c->len) {
        uint32_t hdr;
        memcpy(&hdr, c->wire + c->rd, 4);
        c->rd += 4;
        uint32_t name = hdr & 0x7FFFFFFFu;
        if (name >= c->rcap) {
            size_t nc = c->rcap;
            while (name >= nc) nc *= 2;
            c->rv = realloc(c->rv, nc * 8);
            memset(c->rv + c->rcap, 0, (nc - c->rcap) * 8);
            c->rcap = nc;
        }
        if (hdr & 0x80000000u) {
            memcpy(&c->rv[name], c->wire + c->rd, 8);
            c->rd += 8;
        }
        vals[out++] = c->rv[name];
    }
    return out;
}

uint64_t nmo_chan_bytes(const nmo_chan *c) { return c->bytes; }
