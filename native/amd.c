/* amd — native router for the activation model (phase 14).
 *
 * The spec section-8 realization, complete enough for true benchmarks:
 * the full grammar (LIT/COMP/DEMAND/ERR, LEB128), the entire universal
 * library (concat, emit-disk, select, tally, last, sum, sort, div, sub,
 * pick, uniq), promoted zero-operand templates from <world>/lib, and
 * the phase-1 wire protocol (instructions in, literal/error node out)
 * on a single-threaded event loop — one router, firings never yield.
 * Byte-compatible with every world the Python runtime ever wrote.
 * Out of scope (refused, not mis-fired): promoted shapes with operand
 * slots.
 *
 * Semantics ported exactly from am/structures.py: delimiter is a
 * terminator; numbers are strict decimal ASCII (optional leading '-');
 * div is floor division and refuses on zero; sort modes num/numdesc/
 * text/textdesc; pick ops ge/gt/le/lt/eq; refusals abort the whole
 * firing and return an ERR node.
 *
 * cc -O2 -o amd amd.c
 * usage: amd <world> <port>
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
#include <sys/socket.h>
#include <sys/stat.h>
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

static const char *g_world;

typedef struct { uint8_t *p; size_t len, cap; } buf_t;

static void oom(void) { fprintf(stderr, "amd: out of memory\n"); exit(1); }

static void bgrow(buf_t *b, size_t need) {
    if (b->len + need <= b->cap) return;
    size_t cap = b->cap ? b->cap : 64;
    while (cap < b->len + need) cap *= 2;
    b->p = realloc(b->p, cap);
    if (!b->p) oom();
    b->cap = cap;
}

static void bput(buf_t *b, const void *src, size_t n) {
    bgrow(b, n);
    memcpy(b->p + b->len, src, n);
    b->len += n;
}

/* ---- refusals: abort the whole firing, propagate to the demander ---- */

static jmp_buf g_refuse_jmp;
static char g_refuse_msg[512];

static void refuse(const char *fmt, const char *arg) {
    snprintf(g_refuse_msg, sizeof g_refuse_msg, fmt, arg ? arg : "");
    longjmp(g_refuse_jmp, 1);
}

/* ---- varints ---- */

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

static void wv(buf_t *b, uint64_t n) {
    do {
        uint8_t c = n & 0x7F;
        n >>= 7;
        if (n) c |= 0x80;
        bput(b, &c, 1);
    } while (n);
}

/* framing: end offset of one node, -1 if incomplete, -2 if not an
   instruction. Mirrors am/instruction.py skip(). */
static ssize_t skip_node(const uint8_t *b, size_t len, size_t off) {
    if (off >= len) return -1;
    uint8_t tag = b[off++];
    if (tag == LIT || tag == DEMAND || tag == ERR) {
        uint64_t n = 0;
        int shift = 0;
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
        uint64_t argc = 0;
        int shift = 0;
        for (int field = 0; field < 2; field++) {   /* sid then argc */
            uint64_t n = 0;
            shift = 0;
            for (;;) {
                if (off >= len) return -1;
                uint8_t c = b[off++];
                n |= (uint64_t)(c & 0x7F) << shift;
                if (!(c & 0x80)) break;
                shift += 7;
            }
            if (field == 1) argc = n;
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

/* ---- world I/O ---- */

static uint8_t *read_whole(const char *path, size_t *out_len) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return NULL;
    struct stat st;
    if (fstat(fd, &st) != 0) { close(fd); return NULL; }
    uint8_t *p = malloc(st.st_size ? st.st_size : 1);
    if (!p) oom();
    size_t got = 0;
    while (got < (size_t)st.st_size) {
        ssize_t r = read(fd, p + got, st.st_size - got);
        if (r <= 0) { close(fd); free(p); return NULL; }
        got += r;
    }
    close(fd);
    *out_len = got;
    return p;
}

static void ref_path(char *out, size_t outsz, const uint8_t *ref, size_t n) {
    if (n == 0 || ref[0] == '/' || memmem(ref, n, "..", 2))
        refuse("bad reference", NULL);
    if (snprintf(out, outsz, "%s/%.*s", g_world, (int)n, ref) >= (int)outsz)
        refuse("reference too long", NULL);
}

static void mkdirs_for(const char *path) {
    char tmp[8192];
    snprintf(tmp, sizeof tmp, "%s", path);
    for (char *p = tmp + 1; *p; p++)
        if (*p == '/') { *p = 0; mkdir(tmp, 0755); *p = '/'; }
}

/* ---- number and segment helpers (semantics of am/structures.py) ---- */

static long long to_num(const uint8_t *p, size_t n) {
    if (n == 0) refuse("not a number: %s", "");
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

/* delimiter is a terminator: trailing empty segment is dropped */
static slice_t *segments(const uint8_t *hay, size_t hn,
                         const uint8_t *delim, size_t dn, size_t *count) {
    if (dn == 0) refuse("empty delimiter", NULL);
    size_t cap = 16, n = 0;
    slice_t *seg = malloc(cap * sizeof *seg);
    if (!seg) oom();
    size_t start = 0;
    while (start <= hn) {
        const uint8_t *hit = hn > start
            ? memmem(hay + start, hn - start, delim, dn) : NULL;
        size_t end = hit ? (size_t)(hit - hay) : hn;
        if (!hit && end == start) break;   /* trailing empty dropped / done */
        if (n == cap) {
            cap *= 2;
            seg = realloc(seg, cap * sizeof *seg);
            if (!seg) oom();
        }
        seg[n].p = hay + start;
        seg[n].len = end - start;
        n++;
        if (!hit) break;
        start = end + dn;
    }
    *count = n;
    return seg;
}

static int contains(slice_t s, const uint8_t *needle, size_t n) {
    if (n == 0) return 1;
    return s.len >= n && memmem(s.p, s.len, needle, n) != NULL;
}

static void join_terminated(buf_t *out, slice_t *seg, size_t n,
                            const uint8_t *delim, size_t dn) {
    for (size_t i = 0; i < n; i++) {
        bput(out, seg[i].p, seg[i].len);
        bput(out, delim, dn);
    }
}

/* ---- resident templates ---- */

static buf_t g_tmpl[MAX_SID];
static int g_tmpl_loaded[MAX_SID];

/* ---- firing (value-returning) ---- */

static buf_t fire_value(const uint8_t *b, size_t len, size_t *off, int depth);

static buf_t demand_fire(const uint8_t *ref, size_t n, int depth) {
    /* static: keeps the recursive frame tiny (chains recurse thousands
       deep); consumed fully before the recursion below, single loop */
    static char path[8192];
    ref_path(path, sizeof path, ref, n);
    size_t flen;
    uint8_t *fbuf = read_whole(path, &flen);
    if (!fbuf) refuse("no such reference: %s", path);
    size_t foff = 0;
    buf_t v = fire_value(fbuf, flen, &foff, depth + 1);
    if (foff != flen) {
        free(fbuf);
        refuse("trailing bytes in stored instruction", NULL);
    }
    free(fbuf);
    return v;
}

static const uint8_t *g_sort_delim;   /* comparator context */
static size_t g_sort_dn;
static int g_sort_num, g_sort_desc, g_sort_bad;

static int cmp_slice(const void *a, const void *b) {
    const slice_t *x = a, *y = b;
    int r;
    if (g_sort_num) {
        long long nx, ny;
        /* to_num refuses via longjmp; pre-validated before qsort */
        nx = 0; ny = 0;
        for (size_t i = (x->p[0] == '-'); i < x->len; i++) nx = nx * 10 + (x->p[i] - '0');
        if (x->len && x->p[0] == '-') nx = -nx;
        for (size_t i = (y->p[0] == '-'); i < y->len; i++) ny = ny * 10 + (y->p[i] - '0');
        if (y->len && y->p[0] == '-') ny = -ny;
        r = (nx > ny) - (nx < ny);
    } else {
        size_t m = x->len < y->len ? x->len : y->len;
        r = memcmp(x->p, y->p, m);
        if (!r) r = (x->len > y->len) - (x->len < y->len);
    }
    return g_sort_desc ? -r : r;
}

static buf_t dispatch(uint64_t sid, buf_t *v, uint64_t argc, int depth) {
    buf_t out = {0};
    (void)depth;
    if (sid == S_CONCAT) {
        for (uint64_t i = 0; i < argc; i++) bput(&out, v[i].p, v[i].len);
        return out;
    }
    if (sid == S_EMIT) {
        if (argc != 2) refuse("emit-disk takes (reference, value)", NULL);
        static char path[8192];   /* dispatch never overlaps itself */
        ref_path(path, sizeof path, v[0].p, v[0].len);
        mkdirs_for(path);
        int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) refuse("cannot emit: %s", path);
        size_t done = 0;
        while (done < v[1].len) {
            ssize_t w = write(fd, v[1].p + done, v[1].len - done);
            if (w <= 0) { close(fd); refuse("emit failed: %s", path); }
            done += w;
        }
        close(fd);
        bput(&out, v[0].p, v[0].len);
        return out;
    }
    if (sid == S_SELECT || sid == S_TALLY || sid == S_PICK) {
        if ((sid == S_PICK && argc != 4) || (sid != S_PICK && argc != 3))
            refuse("wrong arity", NULL);
        size_t n;
        slice_t *seg = segments(v[0].p, v[0].len, v[1].p, v[1].len, &n);
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
        long long count = 0;
        for (size_t i = 0; i < n; i++) {
            int keep;
            if (sid == S_PICK) {
                long long a = to_num(seg[i].p, seg[i].len);
                keep = (op == 0 && a >= t) || (op == 1 && a > t) ||
                       (op == 2 && a <= t) || (op == 3 && a < t) ||
                       (op == 4 && a == t);
            } else {
                keep = contains(seg[i], v[2].p, v[2].len);
            }
            if (!keep) continue;
            if (sid == S_TALLY) count++;
            else { bput(&out, seg[i].p, seg[i].len); bput(&out, v[1].p, v[1].len); }
        }
        free(seg);
        if (sid == S_TALLY) {
            char tmp[32];
            bput(&out, tmp, snprintf(tmp, sizeof tmp, "%lld", count));
        }
        return out;
    }
    if (sid == S_LAST) {
        if (argc != 3) refuse("last takes (value, delimiter, count)", NULL);
        long long k = to_num(v[2].p, v[2].len);
        if (k < 0 || (v[2].len && v[2].p[0] == '-'))
            refuse("last: count must be decimal digits", NULL);
        size_t n;
        slice_t *seg = segments(v[0].p, v[0].len, v[1].p, v[1].len, &n);
        size_t from = (size_t)k >= n ? 0 : n - (size_t)k;
        if (k > 0)
            join_terminated(&out, seg + from, n - from, v[1].p, v[1].len);
        free(seg);
        return out;
    }
    if (sid == S_SUM) {
        if (argc != 2) refuse("sum takes (value, delimiter)", NULL);
        size_t n;
        slice_t *seg = segments(v[0].p, v[0].len, v[1].p, v[1].len, &n);
        long long total = 0;
        for (size_t i = 0; i < n; i++) total += to_num(seg[i].p, seg[i].len);
        free(seg);
        char tmp[32];
        bput(&out, tmp, snprintf(tmp, sizeof tmp, "%lld", total));
        return out;
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
        slice_t *seg = segments(v[0].p, v[0].len, v[1].p, v[1].len, &n);
        if (g_sort_num)   /* validate strictly before the comparator runs */
            for (size_t i = 0; i < n; i++) to_num(seg[i].p, seg[i].len);
        qsort(seg, n, sizeof *seg, cmp_slice);
        join_terminated(&out, seg, n, v[1].p, v[1].len);
        free(seg);
        return out;
    }
    if (sid == S_DIV || sid == S_SUB) {
        if (argc != 2) refuse("takes two numbers", NULL);
        long long a = to_num(v[0].p, v[0].len), b = to_num(v[1].p, v[1].len);
        long long r;
        if (sid == S_SUB) {
            r = a - b;
        } else {
            if (b == 0) refuse("division by zero", NULL);
            r = a / b;                       /* floor like Python's // */
            if ((a % b != 0) && ((a < 0) != (b < 0))) r--;
        }
        char tmp[32];
        bput(&out, tmp, snprintf(tmp, sizeof tmp, "%lld", r));
        return out;
    }
    if (sid == S_UNIQ) {
        if (argc != 2) refuse("uniq takes (value, delimiter)", NULL);
        size_t n;
        slice_t *seg = segments(v[0].p, v[0].len, v[1].p, v[1].len, &n);
        for (size_t i = 0; i < n; i++) {
            if (i && seg[i].len == seg[i - 1].len &&
                    !memcmp(seg[i].p, seg[i - 1].p, seg[i].len))
                continue;
            bput(&out, seg[i].p, seg[i].len);
            bput(&out, v[1].p, v[1].len);
        }
        free(seg);
        return out;
    }
    if (sid >= PROMOTED_BASE && sid < MAX_SID && g_tmpl_loaded[sid]) {
        if (argc != 0)
            refuse("promoted shapes with operand slots: not in amd scope", NULL);
        bput(&out, g_tmpl[sid].p, g_tmpl[sid].len);
        return out;
    }
    refuse("unknown structure id %s", NULL);
    return out;
}

static buf_t fire_value(const uint8_t *b, size_t len, size_t *off, int depth) {
    if (depth > MAX_DEPTH) refuse("demand too deep", NULL);
    if (*off >= len) refuse("truncated instruction", NULL);
    uint8_t tag = b[(*off)++];
    if (tag == LIT) {
        uint64_t n = rv(b, len, off);
        if (*off + n > len) refuse("truncated literal", NULL);
        buf_t v = {0};
        bput(&v, b + *off, n);
        *off += n;
        return v;
    }
    if (tag == COMP) {
        uint64_t sid = rv(b, len, off);
        uint64_t argc = rv(b, len, off);
        if (argc > 65536) refuse("absurd arity", NULL);
        buf_t *vals = calloc(argc ? argc : 1, sizeof *vals);
        if (!vals) oom();
        for (uint64_t i = 0; i < argc; i++)
            vals[i] = fire_value(b, len, off, depth);
        buf_t out = dispatch(sid, vals, argc, depth);
        for (uint64_t i = 0; i < argc; i++) free(vals[i].p);
        free(vals);
        return out;
    }
    if (tag == DEMAND) {
        uint64_t n = rv(b, len, off);
        if (*off + n > len) refuse("truncated reference", NULL);
        buf_t v = demand_fire(b + *off, n, depth);
        *off += n;
        return v;
    }
    if (tag == ERR) {
        uint64_t n = rv(b, len, off);
        char msg[256];
        snprintf(msg, sizeof msg, "%.*s",
                 (int)(n < 200 ? n : 200), b + *off);
        refuse("%s", msg);
    }
    refuse("not an instruction (bad tag)", NULL);
    buf_t none = {0};
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
        char path[8192];
        snprintf(path, sizeof path, "%s/%s", libdir, e->d_name);
        size_t flen;
        uint8_t *fbuf = read_whole(path, &flen);
        if (!fbuf) continue;
        if (setjmp(g_refuse_jmp) == 0) {
            size_t off = 0;
            g_tmpl[sid] = fire_value(fbuf, flen, &off, 0);
            g_tmpl_loaded[sid] = 1;
        }   /* shape bodies with slots refuse: left unloaded, refused on use */
        free(fbuf);
    }
    closedir(d);
}

/* ---- the event loop ---- */

static void serve_conn(int fd) {
    buf_t in = {0};
    uint8_t chunk[65536];
    for (;;) {
        ssize_t r = read(fd, chunk, sizeof chunk);
        if (r <= 0) break;
        bput(&in, chunk, r);
        size_t start = 0;
        for (;;) {
            ssize_t end = skip_node(in.p, in.len, start);
            if (end == -1) break;
            buf_t resp = {0};
            if (end == -2) {
                const char *m = "not an instruction (bad tag)";
                uint8_t t = ERR;
                bput(&resp, &t, 1);
                wv(&resp, strlen(m));
                bput(&resp, m, strlen(m));
                if (write(fd, resp.p, resp.len) < 0) { /* dropping anyway */ }
                free(resp.p);
                free(in.p);
                return;   /* stream is not instructions; drop it */
            }
            if (setjmp(g_refuse_jmp) == 0) {
                size_t off = start;
                buf_t v = fire_value(in.p, (size_t)end, &off, 0);
                uint8_t t = LIT;
                bput(&resp, &t, 1);
                wv(&resp, v.len);
                bput(&resp, v.p, v.len);
                free(v.p);
            } else {
                uint8_t t = ERR;
                bput(&resp, &t, 1);
                wv(&resp, strlen(g_refuse_msg));
                bput(&resp, g_refuse_msg, strlen(g_refuse_msg));
            }
            size_t done = 0;
            while (done < resp.len) {
                ssize_t w = write(fd, resp.p + done, resp.len - done);
                if (w <= 0) { free(resp.p); free(in.p); return; }
                done += w;
            }
            free(resp.p);
            start = (size_t)end;
        }
        if (start) {
            memmove(in.p, in.p + start, in.len - start);
            in.len -= start;
        }
    }
    free(in.p);
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: amd <world> <port>\n");
        return 1;
    }
    g_world = argv[1];
    mkdir(g_world, 0755);
    signal(SIGPIPE, SIG_IGN);
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
        perror("amd: bind/listen");
        return 1;
    }
    fprintf(stderr, "amd: serving %s on 127.0.0.1:%s\n", argv[1], argv[2]);
    for (;;) {
        int c = accept(s, NULL, NULL);
        if (c < 0) continue;
        setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        serve_conn(c);
        close(c);
    }
}
