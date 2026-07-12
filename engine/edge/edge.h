/* The edge: every silicon compromise lives here (see EMULATION.md). */
#ifndef NMO_EDGE_H
#define NMO_EDGE_H

#include "../fabric/fabric.h"
#include <stddef.h>

/* plant.c - builds a fabric from trees (allocates; fabric never does) */
nmo_fabric *nmo_plant(const nmo_tree *trees, uint32_t ntrees,
                      uint32_t ntags, uint32_t name_span,
                      uint64_t *exit_region);
void nmo_unplant(nmo_fabric *f);
int nmo_tree_valid(const nmo_tree *t, uint32_t ntags);

/* pave.c - cc+dlopen paving; swaps road fns in place; 0 on success */
int nmo_pave_all(nmo_fabric *f, const char *dir, const char *cc);

/* name.c - identity assignment at birth (interning; hashing lives
 * here, never in fabric); returns dense name, 0-based */
typedef struct nmo_namer nmo_namer;
nmo_namer *nmo_namer_new(void);
void nmo_namer_del(nmo_namer *n);
uint32_t nmo_name(nmo_namer *n, uint64_t val, int *novel);
uint32_t nmo_name_count(const nmo_namer *n);

/* channel.c - boundary wire: value once (12B), reference after (4B) */
typedef struct nmo_chan nmo_chan;
nmo_chan *nmo_chan_new(nmo_namer *n);
void nmo_chan_del(nmo_chan *c);
size_t nmo_chan_send(nmo_chan *c, const uint64_t *vals, size_t n);
size_t nmo_chan_recv(nmo_chan *c, uint64_t *vals, size_t cap);
uint64_t nmo_chan_bytes(const nmo_chan *c);

/* convert.c - world -> arrivals, shape preserved (G5): emits
 * entropy_before and entropy_after side by side, always. val[] carries
 * up to NMO_MAX_SLOTS independent values per event (richer than a
 * single u64 - real events are not one number); identity (name) is
 * carried from val[0] as before. */
typedef struct {
    uint32_t tag;
    uint32_t name;
    uint64_t val[NMO_MAX_SLOTS];
} nmo_arrival;

typedef struct {
    nmo_arrival *arr;
    size_t n;
    uint32_t ntags;
    double entropy_before;   /* structural signatures, pre-conversion */
    double entropy_after;    /* tag stream, post-conversion */
    char (*tag_sig)[64];     /* tag -> signature text */
    uint32_t name_span;
} nmo_stream;

int nmo_convert_strace(const char *glob_dir, nmo_namer *nm,
                       nmo_stream *out);
void nmo_stream_free(nmo_stream *s);

#endif
