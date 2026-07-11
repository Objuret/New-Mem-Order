/* THE FABRIC - the machine proper (MACHINE.md), and nothing else.
 *
 * BUILD-LAW gates bind this directory. What that means structurally:
 * arrival -> road entry is one indirect dispatch (G1); processing is
 * per-arrival in arrival order, exits leave as bare values in that
 * same order (G2); identity arrives with the datum as a dense name
 * assigned at the edge - the fabric only ever indexes by it, never
 * derives it (G3); a multi-stage computation moves between trees by
 * direct road-to-road firing inside residence, interior values are
 * nameless and unaddressable, and nothing here allocates (G4); this
 * header includes nothing from edge/ and never will (G6).
 *
 * Everything the silicon forced us to compromise lives on the other
 * side of that line, in edge/, registered in EMULATION.md.
 */
#ifndef NMO_FABRIC_H
#define NMO_FABRIC_H

#include <stdint.h>

/* ---- the fixed vocabulary, installed once (layer 3) ---- */
#define NMO_BINOPS(X) \
    X(ADD,  l + r) \
    X(SUB,  l - r) \
    X(MUL,  l * r) \
    X(AND,  l & r) \
    X(OR,   l | r) \
    X(XOR,  l ^ r) \
    X(SHL,  l << (r & 63)) \
    X(SHR,  l >> (r & 63)) \
    X(ROTL, (l << (r & 63)) | (l >> ((64 - (r & 63)) & 63))) \
    X(EQ,   (uint64_t)(l == r)) \
    X(LT,   (uint64_t)(l < r)) \
    X(MIN,  l < r ? l : r) \
    X(MAX,  l > r ? l : r)

typedef enum {
    NMO_OP_INPUT = 0,
    NMO_OP_CONST,
    NMO_OP_SELECT,
#define X(NAME, EXPR) NMO_OP_##NAME,
    NMO_BINOPS(X)
#undef X
    NMO_OP_COUNT
} nmo_op;

#define NMO_MAX_NODES 256
#define NMO_MAX_EXITS 8

/* an exit either leaves the machine (boundary) or feeds another tree
 * in residence (layer 4: circulation is real) */
#define NMO_EXIT_BOUNDARY 0xFFFFFFFFu

typedef struct {
    uint8_t op;
    uint16_t a, b, c;       /* operand nodes; always earlier nodes */
    uint64_t imm;           /* NMO_OP_CONST only */
} nmo_node;

typedef struct {
    uint32_t tag;
    uint16_t nnodes;
    uint16_t nexits;
    nmo_node nodes[NMO_MAX_NODES];
    uint16_t exits[NMO_MAX_EXITS];       /* exit nodes */
    uint32_t exit_to[NMO_MAX_EXITS];     /* NMO_EXIT_BOUNDARY or a tag */
} nmo_tree;

/* ---- the fabric ---- */
typedef struct nmo_fabric nmo_fabric;

/* a road takes the fabric and the arriving value; the tree pointer
 * lets one generic walker serve any unpaved road (the single slow
 * road, layer 1) while paved roads ignore it */
typedef void (*nmo_road_fn)(nmo_fabric *, const nmo_tree *, uint64_t);

typedef struct {
    nmo_road_fn fn;
    const nmo_tree *tree;
} nmo_road;

struct nmo_fabric {
    nmo_road *roads;            /* tag-indexed; the road table, hot */
    uint32_t ntags;
    /* the boundary: exit values land here, in arrival order (G2) */
    uint64_t *exit_at;
    /* the result matrix (layer 5): a concluded arrival replays ALL
     * its chain's boundary exits from one indexed block; stride =
     * exits per firing of that tag's chain (0 = no matrix) */
    uint64_t *matrix;
    uint64_t *matrix_meta;      /* tag -> (offset << 4) | stride; NULL
                                   when every root is single-exit and
                                   the matrix is indexed by (tag,name)
                                   directly */
    uint8_t *matrix_ok;         /* single-exit layout: tag eligible */
    uint8_t *matrix_known;      /* (tag, name) -> concluded */
    uint32_t name_span;         /* names >= span bypass the matrix */
};

/* arrival: the datum announces its road (layer 2); one indirect
 * dispatch from here to road entry (G1). The exit cursor travels by
 * value so concluded arrivals never touch fabric state. */
static inline uint64_t *nmo_arrive_at(nmo_fabric *f, uint32_t tag,
                                      uint32_t name, uint64_t x,
                                      uint64_t *at) {
    if (!f->matrix || name >= f->name_span) {
        f->exit_at = at;
        nmo_road *r = &f->roads[tag];
        r->fn(f, r->tree, x);            /* the one indirect dispatch */
        return f->exit_at;
    }
    {
        uint64_t kn = (uint64_t)tag * f->name_span + name;
        if (!f->matrix_meta) {          /* every root concludes once */
            if (f->matrix_known[kn]) {
                *at++ = f->matrix[kn];
                return at;
            }
            f->exit_at = at;
            nmo_road *r = &f->roads[tag];
            r->fn(f, r->tree, x);
            at = f->exit_at;
            if (f->matrix_ok[tag]) {
                f->matrix[kn] = at[-1];
                f->matrix_known[kn] = 1;
            }
            return at;
        }
        uint64_t meta = f->matrix_meta[tag];
        uint32_t st = (uint32_t)(meta & 15);
        if (st) {
            uint64_t k = (meta >> 4) + (uint64_t)name * st;
            if (f->matrix_known[kn]) {
                for (uint32_t j = 0; j < st; j++)
                    *at++ = f->matrix[k + j];
                return at;
            }
            f->exit_at = at;
            nmo_road *r = &f->roads[tag];
            r->fn(f, r->tree, x);
            at = f->exit_at;
            for (uint32_t j = 0; j < st; j++)
                f->matrix[k + j] = (at - st)[j];
            f->matrix_known[kn] = 1;
            return at;
        }
    }
    f->exit_at = at;
    nmo_road *r = &f->roads[tag];
    r->fn(f, r->tree, x);
    return f->exit_at;
    /* (matrix layouts above; a tag with no matrix falls through) */
}

static inline void nmo_arrive_inl(nmo_fabric *f, uint32_t tag,
                                  uint32_t name, uint64_t x) {
    f->exit_at = nmo_arrive_at(f, tag, name, x, f->exit_at);
}

void nmo_arrive(nmo_fabric *f, uint32_t tag, uint32_t name, uint64_t x);
void nmo_road_entry(nmo_fabric *f, uint32_t tag, uint64_t x);

/* the single slow road: one generic walker, fabric-resident */
void nmo_walk_road(nmo_fabric *f, const nmo_tree *t, uint64_t x);

#endif
