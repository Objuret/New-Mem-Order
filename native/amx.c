/* amx — the activation model engine built FOR the machine (phase 17).
 *
 * amd (phase 14) was a C translation of the Python router's
 * architecture: a file per instruction, an open()/read() per demand, a
 * malloc and a copy per value. This is the spec section-8 realization
 * proper, designed around the data path:
 *
 *   - THE WORLD IS ONE MMAP'D PACK. Unsent instructions live
 *     back-to-back in an append-only container file, mapped once.
 *     A reference is an offset-name ("@1f4a"); demanding it is pointer
 *     arithmetic into the mapping — no syscall, no inode, no dentry.
 *     (DECISIONS 2.4, ruled: a reference may name into a container.
 *     Mutable heads remain small files at the world's edge; file-path
 *     references still resolve for compatibility.)
 *   - VALUES ARE SLICES. A literal fires to a pointer into the pack
 *     (or wire buffer); a template reference fires to a pointer into
 *     the resident library blob. Bytes are copied at most once, into
 *     a per-request bump arena (one mmap'd region, reset per request,
 *     never moved — no malloc in the hot path).
 *   - THE LIBRARY IS RESIDENT BY CONSTRUCTION: dispatch is a switch,
 *     templates are one contiguous blob loaded at start, both sized to
 *     live in cache.
 *   - EMIT APPENDS. emit-disk with the reserved name "@" appends the
 *     value to the pack tail and returns the assigned offset-name —
 *     the demander holds the returned reference (the phase-1 pattern).
 *     A crash can only strand unreferenced tail bytes: heads are
 *     written after appends inside a firing, so consistency is still
 *     structural, not coded.
 *
 * Grammar, structure set, wire protocol: unchanged and byte-compatible.
 *
 * cc -O2 -o amx amx.c
 * usage: amx <world> <port>
 */

#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dirent.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <unistd.h>

#define LIT 0x01
#define COMP 0x02
#define DEMAND 0x03
#define ERR 0x04

enum { S_CONCAT = 1, S_EMIT = 2, S_SELECT = 3, S_TALLY = 4, S_LAST = 5,
       S_SUM = 6, S_SORT = 7, S_DIV = 8, S_SUB = 9, S_PICK = 10,
       S_UNIQ = 11 };
#define PROMOTED_BASE 100
#define MAX_SID 4096
#define MAX_DEPTH 8192

#define PACK_RESERVE (1ULL << 33)   /* 8 GiB of address space, sparse */
#define ARENA_RESERVE (1ULL << 30)  /* 1 GiB bump arena, reset per request */

static const char *g_world;
static int g_pack_fd;
static uint8_t *g_pack;             /* MAP_SHARED view of the pack file */
static size_t g_tail;               /* bytes actually in the pack */
static size_t g_file_size;          /* current ftruncate'd size */

static uint8_t *g_arena;
static size_t g_arena_used;

typedef struct { const uint8_t *p; size_t len; } val_t;

/* resident templates: one contiguous blob + a slice table */
static val_t g_tmpl[MAX_SID];
static int g_tmpl_loaded[MAX_SID];

static jmp_buf g_refuse_jmp;
static char g_refuse_msg[512];

static void refuse(const char *fmt, const char *arg) {
    snprintf(g_refuse_msg, sizeof g_refuse_msg, fmt, arg ? arg : "");
    longjmp(g_refuse_jmp, 1);
}

static uint8_t *arena_alloc(size_t n) {
    if (g_arena_used + n > ARENA_RESERVE) refuse("arena exhausted", NULL);
    uint8_t *p = g_arena + g_arena_used;
    g_arena_used += n;
    return p;
}

static uint64_t rv(const uint8_t *b, size_t len, size_t *off) {
    uint64_t n = 0;
    int shift = 0;
    for (;;) {
        if (*off >= len) refuse("truncated varint", NULL);
        uint8_t c = b[(*off)++];
        n |= (uint64_t)(c & 0x7F) << shift;
        if (!(c & 0x80)) return n;
        shift += 7;
    }
}

/* framing for the wire: end offset, -1 incomplete, -2 not an instruction */
static ssize_t skip_node(const uint8_t *b, size_t len, size_t off) {
    if (off >= len) return -1;
    uint8_t tag = b[off++];
    uint64_t n = 0, argc = 0;
    int shift = 0;
    if (tag == LIT || tag == DEMAND || tag == ERR) {
        for (;;) {
            if (off >= len) return -1;
            uint8_t c = b[off++];
            n |= (uint64_t)(c & 0x7F) << shift;
            if (!(c & 0x80)) break;
            shift += 7;
        }
        if (off + n > len) return -1;
        return (ssize_t)(off + n);
    }
    if (tag == COMP) {
        for (int f = 0; f < 2; f++) {
            n = 0; shift = 0;
            for (;;) {
                if (off >= len) return -1;
                uint8_t c = b[off++];
                n |= (uint64_t)(c & 0x7F) << shift;
                if (!(c & 0x80)) break;
                shift += 7;
            }
            if (f == 1) argc = n;
        }
        for (uint64_t i = 0; i < argc; i++) {
            ssize_t e = skip_node(b, len, off);
            if (e < 0) return e;
            off = e;
        }
        return (ssize_t)off;
    }
    return -2;
}

/* ---- pack append (the emit terminal's fast path) ---- */

static size_t pack_append(const uint8_t *p, size_t n) {
    if (g_tail + n > PACK_RESERVE) refuse("pack full", NULL);
    if (g_tail + n > g_file_size) {
        size_t want = g_file_size ? g_file_size : (1 << 20);
        while (want < g_tail + n) want *= 2;
        if (ftruncate(g_pack_fd, want) != 0) refuse("pack grow failed", NULL);
        g_file_size = want;
    }
    memcpy(g_pack + g_tail, p, n);   /* MAP_SHARED: this IS the write */
    size_t at = g_tail;
    g_tail += n;
    return at;
}

/* persist the tail so restarts know where data ends: the tail is
   derivable (walk from 0), but a tiny side file makes restart O(1);
   it is engineering state like the sync high-water mark */
static void save_tail(void) {
    char path[4096];
    snprintf(path, sizeof path, "%s/tail", g_world);
    char tmp[32];
    int n = snprintf(tmp, sizeof tmp, "%zx", g_tail);
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) { if (write(fd, tmp, n) != n) {} close(fd); }
}

/* ---- helpers shared with amd (identical semantics) ---- */

static long long to_num(const uint8_t *p, size_t n) {
    if (n == 0) refuse("not a number", NULL);
    size_t i = (p[0] == '-') ? 1 : 0;
    if (i >= n) refuse("not a number", NULL);
    long long v = 0;
    for (; i < n; i++) {
        if (p[i] < '0' || p[i] > '9') refuse("not a number", NULL);
        v = v * 10 + (p[i] - '0');
    }
    return p[0] == '-' ? -v : v;
}

typedef struct { const uint8_t *p; size_t len; } slice_t;

static slice_t *segments(val_t hay, val_t delim, size_t *count) {
    if (delim.len == 0) refuse("empty delimiter", NULL);
    size_t cap = 16, n = 0;
    slice_t *seg = malloc(cap * sizeof *seg);
    if (!seg) refuse("oom", NULL);
    size_t start = 0;
    while (start <= hay.len) {
        const uint8_t *hit = hay.len > start
            ? memmem(hay.p + start, hay.len - start, delim.p, delim.len) : NULL;
        size_t end = hit ? (size_t)(hit - hay.p) : hay.len;
        if (!hit && end == start) break;
        if (n == cap) {
            cap *= 2;
            seg = realloc(seg, cap * sizeof *seg);
            if (!seg) refuse("oom", NULL);
        }
        seg[n].p = hay.p + start;
        seg[n].len = end - start;
        n++;
        if (!hit) break;
        start = end + delim.len;
    }
    *count = n;
    return seg;
}

static int contains(slice_t s, val_t needle) {
    if (needle.len == 0) return 1;
    return s.len >= needle.len && memmem(s.p, s.len, needle.p, needle.len);
}

static val_t join_terminated(slice_t *seg, size_t n, val_t delim) {
    size_t total = 0;
    for (size_t i = 0; i < n; i++) total += seg[i].len + delim.len;
    uint8_t *out = arena_alloc(total);
    uint8_t *w = out;
    for (size_t i = 0; i < n; i++) {
        memcpy(w, seg[i].p, seg[i].len); w += seg[i].len;
        memcpy(w, delim.p, delim.len); w += delim.len;
    }
    val_t v = { out, total };
    return v;
}

static val_t num_val(long long x) {
    uint8_t *out = arena_alloc(24);
    int n = snprintf((char *)out, 24, "%lld", x);
    val_t v = { out, (size_t)n };
    return v;
}

static int g_sort_num, g_sort_desc;
static int cmp_slice(const void *a, const void *b) {
    const slice_t *x = a, *y = b;
    int r;
    if (g_sort_num) {
        long long nx = 0, ny = 0;
        for (size_t i = (x->len && x->p[0] == '-'); i < x->len; i++)
            nx = nx * 10 + (x->p[i] - '0');
        if (x->len && x->p[0] == '-') nx = -nx;
        for (size_t i = (y->len && y->p[0] == '-'); i < y->len; i++)
            ny = ny * 10 + (y->p[i] - '0');
        if (y->len && y->p[0] == '-') ny = -ny;
        r = (nx > ny) - (nx < ny);
    } else {
        size_t m = x->len < y->len ? x->len : y->len;
        r = memcmp(x->p, y->p, m);
        if (!r) r = (x->len > y->len) - (x->len < y->len);
    }
    return g_sort_desc ? -r : r;
}

/* ---- firing: slices in, slices out, arena-backed ---- */

static val_t fire_value(const uint8_t *b, size_t len, size_t *off, int depth);

/* demand_ref and dispatch stay OUT of fire_value's frame (noinline):
   fire_value recurses one level per chain link, so its frame size is
   the depth budget — with these separate it is ~200 bytes and the
   MAX_DEPTH refusal fires long before the stack can overflow. */
__attribute__((noinline))
static val_t demand_ref(const uint8_t *ref, size_t n, int depth) {
    if (n >= 2 && ref[0] == '@') {   /* offset-name into the pack */
        size_t at = 0;
        for (size_t i = 1; i < n; i++) {
            uint8_t c = ref[i];
            int d = c >= '0' && c <= '9' ? c - '0'
                  : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
            if (d < 0) refuse("bad offset reference", NULL);
            at = at * 16 + d;
        }
        if (at >= g_tail) refuse("no such reference (offset)", NULL);
        size_t o = at;
        return fire_value(g_pack, g_tail, &o, depth + 1);
    }
    /* file-path reference: compatibility with file worlds (heads, lib) */
    if (n == 0 || ref[0] == '/' || memmem(ref, n, "..", 2))
        refuse("bad reference", NULL);
    static char path[8192];
    if (snprintf(path, sizeof path, "%s/%.*s", g_world, (int)n, ref)
            >= (int)sizeof path)
        refuse("reference too long", NULL);
    int fd = open(path, O_RDONLY);
    if (fd < 0) refuse("no such reference: %s", path);
    struct stat st;
    fstat(fd, &st);
    uint8_t *fb = arena_alloc(st.st_size ? st.st_size : 1);
    size_t got = 0;
    while (got < (size_t)st.st_size) {
        ssize_t r = read(fd, fb + got, st.st_size - got);
        if (r <= 0) { close(fd); refuse("read failed", NULL); }
        got += r;
    }
    close(fd);
    size_t o = 0;
    val_t v = fire_value(fb, got, &o, depth + 1);
    if (o != got) refuse("trailing bytes in stored instruction", NULL);
    return v;
}

__attribute__((noinline))
static val_t dispatch(uint64_t sid, val_t *v, uint64_t argc) {
    val_t out = {0, 0};
    if (sid == S_CONCAT) {
        size_t total = 0;
        for (uint64_t i = 0; i < argc; i++) total += v[i].len;
        uint8_t *w = arena_alloc(total);
        out.p = w; out.len = total;
        for (uint64_t i = 0; i < argc; i++) {
            memcpy(w, v[i].p, v[i].len);
            w += v[i].len;
        }
        return out;
    }
    if (sid == S_EMIT) {
        if (argc != 2) refuse("emit-disk takes (reference, value)", NULL);
        if (v[0].len == 1 && v[0].p[0] == '@') {
            size_t at = pack_append(v[1].p, v[1].len);
            save_tail();
            uint8_t *r = arena_alloc(24);
            int n = snprintf((char *)r, 24, "@%zx", at);
            out.p = r; out.len = (size_t)n;
            return out;
        }
        /* named file (heads, lib): the mutable world edge */
        if (v[0].len == 0 || v[0].p[0] == '/' || memmem(v[0].p, v[0].len, "..", 2))
            refuse("bad reference", NULL);
        static char path[8192], tmp2[8192];
        snprintf(path, sizeof path, "%s/%.*s", g_world, (int)v[0].len, v[0].p);
        snprintf(tmp2, sizeof tmp2, "%s", path);
        for (char *p = tmp2 + 1; *p; p++)
            if (*p == '/') { *p = 0; mkdir(tmp2, 0755); *p = '/'; }
        int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) refuse("cannot emit: %s", path);
        size_t done = 0;
        while (done < v[1].len) {
            ssize_t w = write(fd, v[1].p + done, v[1].len - done);
            if (w <= 0) { close(fd); refuse("emit failed", NULL); }
            done += w;
        }
        close(fd);
        return v[0];
    }
    if (sid == S_SELECT || sid == S_TALLY || sid == S_PICK) {
        if ((sid == S_PICK && argc != 4) || (sid != S_PICK && argc != 3))
            refuse("wrong arity", NULL);
        size_t n;
        slice_t *seg = segments(v[0], v[1], &n);
        long long t = 0;
        int op = 0;
        if (sid == S_PICK) {
            const char *ops[] = {"ge", "gt", "le", "lt", "eq"};
            op = -1;
            for (int i = 0; i < 5; i++)
                if (v[2].len == 2 && !memcmp(v[2].p, ops[i], 2)) op = i;
            if (op < 0) { free(seg); refuse("pick: unknown op", NULL); }
            t = to_num(v[3].p, v[3].len);
        }
        size_t keepn = 0;
        long long count = 0;
        for (size_t i = 0; i < n; i++) {
            int keep;
            if (sid == S_PICK) {
                long long a = to_num(seg[i].p, seg[i].len);
                keep = (op == 0 && a >= t) || (op == 1 && a > t) ||
                       (op == 2 && a <= t) || (op == 3 && a < t) ||
                       (op == 4 && a == t);
            } else {
                keep = contains(seg[i], v[2]);
            }
            if (keep) {
                if (sid == S_TALLY) count++;
                else seg[keepn++] = seg[i];
            }
        }
        if (sid == S_TALLY) { free(seg); return num_val(count); }
        out = join_terminated(seg, keepn, v[1]);
        free(seg);
        return out;
    }
    if (sid == S_LAST) {
        if (argc != 3) refuse("last takes (value, delimiter, count)", NULL);
        if (v[2].len && v[2].p[0] == '-')
            refuse("last: count must be decimal digits", NULL);
        long long k = to_num(v[2].p, v[2].len);
        size_t n;
        slice_t *seg = segments(v[0], v[1], &n);
        size_t from = (size_t)k >= n ? 0 : n - (size_t)k;
        out = k > 0 ? join_terminated(seg + from, n - from, v[1])
                    : (val_t){arena_alloc(0), 0};
        free(seg);
        return out;
    }
    if (sid == S_SUM) {
        if (argc != 2) refuse("sum takes (value, delimiter)", NULL);
        size_t n;
        slice_t *seg = segments(v[0], v[1], &n);
        long long total = 0;
        for (size_t i = 0; i < n; i++) total += to_num(seg[i].p, seg[i].len);
        free(seg);
        return num_val(total);
    }
    if (sid == S_SORT) {
        if (argc != 3) refuse("sort takes (value, delimiter, mode)", NULL);
        g_sort_num = v[2].len >= 3 && !memcmp(v[2].p, "num", 3);
        int text = v[2].len >= 4 && !memcmp(v[2].p, "text", 4);
        if (!g_sort_num && !text) refuse("sort: unknown mode", NULL);
        g_sort_desc = (v[2].len == (size_t)(g_sort_num ? 7 : 8)) &&
                      !memcmp(v[2].p + (g_sort_num ? 3 : 4), "desc", 4);
        if (v[2].len != (size_t)(g_sort_num ? 3 : 4) && !g_sort_desc)
            refuse("sort: unknown mode", NULL);
        size_t n;
        slice_t *seg = segments(v[0], v[1], &n);
        if (g_sort_num)
            for (size_t i = 0; i < n; i++) to_num(seg[i].p, seg[i].len);
        qsort(seg, n, sizeof *seg, cmp_slice);
        out = join_terminated(seg, n, v[1]);
        free(seg);
        return out;
    }
    if (sid == S_DIV || sid == S_SUB) {
        if (argc != 2) refuse("takes two numbers", NULL);
        long long a = to_num(v[0].p, v[0].len), b = to_num(v[1].p, v[1].len);
        long long r;
        if (sid == S_SUB) r = a - b;
        else {
            if (b == 0) refuse("division by zero", NULL);
            r = a / b;
            if ((a % b != 0) && ((a < 0) != (b < 0))) r--;
        }
        return num_val(r);
    }
    if (sid == S_UNIQ) {
        if (argc != 2) refuse("uniq takes (value, delimiter)", NULL);
        size_t n;
        slice_t *seg = segments(v[0], v[1], &n);
        size_t keepn = 0;
        for (size_t i = 0; i < n; i++)
            if (!i || seg[i].len != seg[keepn - 1].len ||
                    memcmp(seg[i].p, seg[keepn - 1].p, seg[i].len))
                seg[keepn++] = seg[i];
        out = join_terminated(seg, keepn, v[1]);
        free(seg);
        return out;
    }
    if (sid >= PROMOTED_BASE && sid < MAX_SID && g_tmpl_loaded[sid]) {
        if (argc != 0) refuse("shape slots: not in amx scope", NULL);
        return g_tmpl[sid];   /* zero copy: slice into the resident blob */
    }
    refuse("unknown structure id", NULL);
    return out;
}

static val_t fire_value(const uint8_t *b, size_t len, size_t *off, int depth) {
    if (depth > MAX_DEPTH) refuse("demand too deep", NULL);
    if (*off >= len) refuse("truncated instruction", NULL);
    uint8_t tag = b[(*off)++];
    if (tag == LIT) {
        uint64_t n = rv(b, len, off);
        if (*off + n > len) refuse("truncated literal", NULL);
        val_t v = { b + *off, n };   /* zero copy: slice into the source */
        *off += n;
        return v;
    }
    if (tag == COMP) {
        uint64_t sid = rv(b, len, off);
        uint64_t argc = rv(b, len, off);
        if (argc > 65536) refuse("absurd arity", NULL);
        val_t stackv[8];
        val_t *vals = argc <= 8 ? stackv : malloc(argc * sizeof *vals);
        if (!vals) refuse("oom", NULL);
        for (uint64_t i = 0; i < argc; i++)
            vals[i] = fire_value(b, len, off, depth);
        val_t out = dispatch(sid, vals, argc);
        if (vals != stackv) free(vals);
        return out;
    }
    if (tag == DEMAND) {
        uint64_t n = rv(b, len, off);
        if (*off + n > len) refuse("truncated reference", NULL);
        val_t v = demand_ref(b + *off, n, depth);
        *off += n;
        return v;
    }
    if (tag == ERR) {
        uint64_t n = rv(b, len, off);
        static char msg[256];   /* off the recursive frame; refuse() exits */
        snprintf(msg, sizeof msg, "%.*s", (int)(n < 200 ? n : 200), b + *off);
        refuse("%s", msg);
    }
    refuse("not an instruction (bad tag)", NULL);
    val_t none = {0, 0};
    return none;
}

static void load_templates(void) {
    char libdir[4096];
    snprintf(libdir, sizeof libdir, "%.4000s/lib", g_world);
    DIR *d = opendir(libdir);
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d))) {
        char *end;
        long sid = strtol(e->d_name, &end, 10);
        if (*end || sid < PROMOTED_BASE || sid >= MAX_SID) continue;
        char path[4608];
        snprintf(path, sizeof path, "%s/%s", libdir, e->d_name);
        int fd = open(path, O_RDONLY);
        if (fd < 0) continue;
        struct stat st;
        fstat(fd, &st);
        uint8_t *fb = malloc(st.st_size);
        if (read(fd, fb, st.st_size) != st.st_size) { close(fd); free(fb); continue; }
        close(fd);
        if (setjmp(g_refuse_jmp) == 0) {
            size_t off = 0;
            g_arena_used = 0;
            val_t v = fire_value(fb, st.st_size, &off, 0);
            uint8_t *keep = malloc(v.len);   /* resident blob, owned */
            memcpy(keep, v.p, v.len);
            g_tmpl[sid].p = keep;
            g_tmpl[sid].len = v.len;
            g_tmpl_loaded[sid] = 1;
        }
        free(fb);
    }
    closedir(d);
}

static void serve_conn(int fd) {
    size_t cap = 1 << 20, len = 0;
    uint8_t *in = malloc(cap);
    for (;;) {
        if (len == cap) { cap *= 2; in = realloc(in, cap); }
        ssize_t r = read(fd, in + len, cap - len);
        if (r <= 0) break;
        len += r;
        size_t start = 0;
        for (;;) {
            ssize_t end = skip_node(in, len, start);
            if (end == -1) break;
            uint8_t hdr[16];
            struct { const uint8_t *p; size_t n; } body;
            if (end == -2) {
                const char *m = "not an instruction (bad tag)";
                hdr[0] = ERR; hdr[1] = (uint8_t)strlen(m);
                if (write(fd, hdr, 2) < 0 || write(fd, m, strlen(m)) < 0) {}
                free(in);
                return;
            }
            g_arena_used = 0;
            if (setjmp(g_refuse_jmp) == 0) {
                size_t off = start;
                val_t v = fire_value(in, (size_t)end, &off, 0);
                body.p = v.p; body.n = v.len;
                hdr[0] = LIT;
            } else {
                body.p = (const uint8_t *)g_refuse_msg;
                body.n = strlen(g_refuse_msg);
                hdr[0] = ERR;
            }
            size_t hn = 1;
            uint64_t x = body.n;
            do { uint8_t c = x & 0x7F; x >>= 7; if (x) c |= 0x80; hdr[hn++] = c; } while (x);
            struct iovec iov[2] = {
                { hdr, hn }, { (void *)body.p, body.n } };
            ssize_t wr = writev(fd, iov, 2);
            if (wr < 0) { free(in); return; }
            start = (size_t)end;
        }
        if (start) {
            memmove(in, in + start, len - start);
            len -= start;
        }
    }
    free(in);
}

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: amx <world> <port>\n"); return 1; }
    g_world = argv[1];
    mkdir(g_world, 0755);
    signal(SIGPIPE, SIG_IGN);

    char packpath[4096];
    snprintf(packpath, sizeof packpath, "%.4000s/pack", g_world);
    g_pack_fd = open(packpath, O_RDWR | O_CREAT, 0644);
    if (g_pack_fd < 0) { perror("pack"); return 1; }
    struct stat st;
    fstat(g_pack_fd, &st);
    g_file_size = st.st_size;
    g_pack = mmap(NULL, PACK_RESERVE, PROT_READ | PROT_WRITE, MAP_SHARED,
                  g_pack_fd, 0);
    if (g_pack == MAP_FAILED) { perror("mmap pack"); return 1; }
    /* restart: recover the tail (O(1) via side file; the pack itself is
       the truth — the side file is derivable state) */
    g_tail = 0;
    char tp[4300];
    snprintf(tp, sizeof tp, "%s/tail", g_world);
    FILE *tf = fopen(tp, "r");
    if (tf) { if (fscanf(tf, "%zx", &g_tail) != 1) g_tail = 0; fclose(tf); }
    if (g_tail > (size_t)st.st_size) g_tail = st.st_size;

    g_arena = mmap(NULL, ARENA_RESERVE, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (g_arena == MAP_FAILED) { perror("mmap arena"); return 1; }

    load_templates();

    int s = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    addr.sin_port = htons(atoi(argv[2]));
    if (bind(s, (struct sockaddr *)&addr, sizeof addr) != 0 ||
            listen(s, 16) != 0) {
        perror("amx: bind/listen");
        return 1;
    }
    fprintf(stderr, "amx: %s on 127.0.0.1:%s (pack tail %zx)\n",
            argv[1], argv[2], g_tail);
    for (;;) {
        int c = accept(s, NULL, NULL);
        if (c < 0) continue;
        setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        serve_conn(c);
        close(c);
    }
}
