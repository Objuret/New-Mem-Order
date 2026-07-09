/* amfire — native fire loop for the activation model (phase 11).
 *
 * Byte-compatible with am/instruction.py: same grammar (LIT 0x01,
 * COMP 0x02, DEMAND 0x03, ERR 0x04), same LEB128 varints, same stored
 * worlds. Scope: the READ path of layer stores — firing chains built
 * from literals, concat compositions, demands, and promoted zero-operand
 * content templates (everything a condensed store contains). Writes and
 * the full query library stay in the Python runtime; this program exists
 * to measure whether reading-as-firing runs at hardware speed once the
 * interpreter is native (spec section 8's realization, spec section 0's
 * performance claim).
 *
 * Modes:
 *   amfire render    <store> <ref>     fire one stored file to stdout
 *   amfire renderall <store> [outdir]  fire every file under fs/;
 *                                      without outdir: discard, print stats
 *   amfire readall   <dir>             baseline: raw-read the same bytes
 *
 * cc -O2 -o amfire amfire.c
 */

#include <dirent.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define LIT 0x01
#define COMP 0x02
#define DEMAND 0x03
#define ERR 0x04
#define CONCAT 1
#define PROMOTED_BASE 100
#define MAX_SID 4096
#define MAX_DEPTH 4096

static const char *g_store;

typedef struct { uint8_t *p; size_t len, cap; } buf_t;

static void die(const char *msg, const char *arg) {
    fprintf(stderr, "amfire: %s%s%s\n", msg, arg ? ": " : "", arg ? arg : "");
    exit(1);
}

static void grow(buf_t *b, size_t need) {
    if (b->len + need <= b->cap) return;
    size_t cap = b->cap ? b->cap : 4096;
    while (cap < b->len + need) cap *= 2;
    b->p = realloc(b->p, cap);
    if (!b->p) die("out of memory", NULL);
    b->cap = cap;
}

static void put(buf_t *b, const uint8_t *src, size_t n) {
    grow(b, n);
    memcpy(b->p + b->len, src, n);
    b->len += n;
}

static uint8_t *read_file(const char *path, size_t *out_len) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return NULL;
    struct stat st;
    if (fstat(fd, &st) != 0) { close(fd); return NULL; }
    uint8_t *p = malloc(st.st_size ? st.st_size : 1);
    if (!p) die("out of memory", path);
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

static uint64_t uv(const uint8_t *b, size_t len, size_t *off) {
    uint64_t n = 0;
    int shift = 0;
    for (;;) {
        if (*off >= len) die("truncated varint", NULL);
        uint8_t c = b[(*off)++];
        n |= (uint64_t)(c & 0x7F) << shift;
        if (!(c & 0x80)) return n;
        shift += 7;
    }
}

/* resident templates, loaded once from <store>/lib */
static buf_t g_tmpl[MAX_SID];
static int g_tmpl_loaded[MAX_SID];

static void fire(const uint8_t *b, size_t len, size_t *off, buf_t *out, int depth);

static void demand_ref(const char *ref, size_t reflen, buf_t *out, int depth) {
    if (reflen == 0 || ref[0] == '/' || memmem(ref, reflen, "..", 2))
        die("bad reference", ref);
    char path[8192];
    if (snprintf(path, sizeof path, "%s/%.*s", g_store, (int)reflen, ref)
            >= (int)sizeof path)
        die("reference too long", NULL);
    size_t flen;
    uint8_t *fbuf = read_file(path, &flen);
    if (!fbuf) die("no such reference", path);
    size_t foff = 0;
    fire(fbuf, flen, &foff, out, depth + 1);
    if (foff != flen) die("trailing bytes in stored instruction", path);
    free(fbuf);
}

static void fire(const uint8_t *b, size_t len, size_t *off, buf_t *out, int depth) {
    if (depth > MAX_DEPTH) die("demand too deep", NULL);
    if (*off >= len) die("truncated instruction", NULL);
    uint8_t tag = b[(*off)++];
    if (tag == LIT) {
        uint64_t n = uv(b, len, off);
        if (*off + n > len) die("truncated literal", NULL);
        put(out, b + *off, n);
        *off += n;
    } else if (tag == COMP) {
        uint64_t sid = uv(b, len, off);
        uint64_t argc = uv(b, len, off);
        if (sid == CONCAT) {
            /* concat: children fire in order into the same output */
            for (uint64_t i = 0; i < argc; i++)
                fire(b, len, off, out, depth);
        } else if (sid >= PROMOTED_BASE && sid < MAX_SID && argc == 0
                   && g_tmpl_loaded[sid]) {
            put(out, g_tmpl[sid].p, g_tmpl[sid].len);
        } else {
            char msg[64];
            snprintf(msg, sizeof msg, "%llu", (unsigned long long)sid);
            die("structure not in native render scope", msg);
        }
    } else if (tag == DEMAND) {
        uint64_t n = uv(b, len, off);
        if (*off + n > len) die("truncated reference", NULL);
        demand_ref((const char *)(b + *off), n, out, depth);
        *off += n;
    } else if (tag == ERR) {
        uint64_t n = uv(b, len, off);
        fprintf(stderr, "amfire: refusal: %.*s\n", (int)n, b + *off + 0);
        exit(1);
    } else {
        die("not an instruction (bad tag)", NULL);
    }
}

static void load_templates(void) {
    char libdir[4096];
    snprintf(libdir, sizeof libdir, "%s/lib", g_store);
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
        uint8_t *fbuf = read_file(path, &flen);
        if (!fbuf) die("unreadable template", path);
        size_t off = 0;
        buf_t out = {0};
        fire(fbuf, flen, &off, &out, 0);   /* templates are pure; fire once */
        free(fbuf);
        g_tmpl[sid] = out;
        g_tmpl_loaded[sid] = 1;
    }
    closedir(d);
}

/* fire a head, extract field 2 (the chain reference) from its record */
static void chain_of(const char *headref, char *chain, size_t chainsz,
                     char *ftype) {
    buf_t rec = {0};
    demand_ref(headref, strlen(headref), &rec, 0);
    /* five "\n"-terminated fields: type, chain ref, size, mtime, mode */
    uint8_t *nl1 = memchr(rec.p, '\n', rec.len);
    if (!nl1) die("bad head record", headref);
    uint8_t *nl2 = memchr(nl1 + 1, '\n', rec.p + rec.len - nl1 - 1);
    if (!nl2) die("bad head record", headref);
    *ftype = rec.p[0];
    size_t n = nl2 - nl1 - 1;
    if (n + 1 > chainsz) die("chain ref too long", headref);
    memcpy(chain, nl1 + 1, n);
    chain[n] = 0;
    free(rec.p);
}

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static uint64_t g_files, g_bytes, g_fold;

static void fold(buf_t *b) {
    uint64_t x = 0;
    for (size_t i = 0; i < b->len; i++) x = x * 131 + b->p[i];
    g_fold ^= x;
}

static void mkdirs_for(const char *path) {
    char tmp[8192];
    snprintf(tmp, sizeof tmp, "%s", path);
    for (char *p = tmp + 1; *p; p++)
        if (*p == '/') { *p = 0; mkdir(tmp, 0755); *p = '/'; }
}

static void walk_fs(const char *fsdir, const char *rel, const char *outdir) {
    char dirpath[4096];
    snprintf(dirpath, sizeof dirpath, "%s%s%s", fsdir, *rel ? "/" : "", rel);
    DIR *d = opendir(dirpath);
    if (!d) die("cannot open", dirpath);
    struct dirent *e;
    while ((e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char sub[3072];
        snprintf(sub, sizeof sub, "%s%s%s", rel, *rel ? "/" : "", e->d_name);
        char full[8192];
        snprintf(full, sizeof full, "%s/%s", fsdir, sub);
        struct stat st;
        if (lstat(full, &st) != 0) die("stat", full);
        if (S_ISDIR(st.st_mode)) {
            walk_fs(fsdir, sub, outdir);
            continue;
        }
        char headref[8192];
        snprintf(headref, sizeof headref, "fs/%s", sub);
        char chain[4096], ftype;
        chain_of(headref, chain, sizeof chain, &ftype);
        buf_t out = {0};
        demand_ref(chain, strlen(chain), &out, 0);
        g_files++;
        g_bytes += out.len;
        if (outdir && ftype == 'f') {
            char dst[8192];
            snprintf(dst, sizeof dst - 1, "%s/%s", outdir, sub);
            mkdirs_for(dst);
            FILE *f = fopen(dst, "wb");
            if (!f) die("cannot write", dst);
            fwrite(out.p, 1, out.len, f);
            fclose(f);
        } else {
            fold(&out);
        }
        free(out.p);
    }
    closedir(d);
}

static void walk_raw(const char *dir, const char *rel) {
    char dirpath[4096];
    snprintf(dirpath, sizeof dirpath, "%s%s%s", dir, *rel ? "/" : "", rel);
    DIR *d = opendir(dirpath);
    if (!d) die("cannot open", dirpath);
    struct dirent *e;
    while ((e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char sub[3072];
        snprintf(sub, sizeof sub, "%s%s%s", rel, *rel ? "/" : "", e->d_name);
        char full[8192];
        snprintf(full, sizeof full, "%s/%s", dir, sub);
        struct stat st;
        if (lstat(full, &st) != 0) die("stat", full);
        if (S_ISDIR(st.st_mode)) { walk_raw(dir, sub); continue; }
        if (!S_ISREG(st.st_mode)) continue;
        size_t n;
        uint8_t *p = read_file(full, &n);
        if (!p) die("read", full);
        buf_t b = { p, n, n };
        fold(&b);
        g_files++;
        g_bytes += n;
        free(p);
    }
    closedir(d);
}

int main(int argc, char **argv) {
    if (argc >= 3 && !strcmp(argv[1], "render")) {
        g_store = argv[2];
        if (argc != 4) die("usage: amfire render <store> <ref>", NULL);
        load_templates();
        buf_t out = {0};
        demand_ref(argv[3], strlen(argv[3]), &out, 0);
        fwrite(out.p, 1, out.len, stdout);
        return 0;
    }
    if (argc >= 3 && !strcmp(argv[1], "renderall")) {
        g_store = argv[2];
        const char *outdir = argc > 3 ? argv[3] : NULL;
        double t0 = now();
        load_templates();
        char fsdir[4096];
        snprintf(fsdir, sizeof fsdir, "%s/fs", g_store);
        walk_fs(fsdir, "", outdir);
        double dt = now() - t0;
        fprintf(stderr,
                "renderall: %llu files, %llu bytes, %.4fs, %.1f MB/s, fold=%016llx\n",
                (unsigned long long)g_files, (unsigned long long)g_bytes, dt,
                g_bytes / 1e6 / dt, (unsigned long long)g_fold);
        printf("{\"files\": %llu, \"bytes\": %llu, \"seconds\": %.4f}\n",
               (unsigned long long)g_files, (unsigned long long)g_bytes, dt);
        return 0;
    }
    if (argc == 3 && !strcmp(argv[1], "readall")) {
        double t0 = now();
        walk_raw(argv[2], "");
        double dt = now() - t0;
        fprintf(stderr,
                "readall: %llu files, %llu bytes, %.4fs, %.1f MB/s, fold=%016llx\n",
                (unsigned long long)g_files, (unsigned long long)g_bytes, dt,
                g_bytes / 1e6 / dt, (unsigned long long)g_fold);
        printf("{\"files\": %llu, \"bytes\": %llu, \"seconds\": %.4f}\n",
               (unsigned long long)g_files, (unsigned long long)g_bytes, dt);
        return 0;
    }
    die("usage: amfire render|renderall <store> [ref|outdir] | readall <dir>",
        NULL);
}
