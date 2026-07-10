/* membench — phase 16: the memory path, measured (spec section 0's
 * actual mechanism).
 *
 * The claim under test, in machine terms: a small structure set stays
 * resident in cache by virtue of being small and hot, and traffic
 * shrinks to references + values — so the memory system moves fewer
 * bytes and misses less for the same delivered work. The risk under
 * test: reference-chasing adds misses instead.
 *
 * Two in-memory representations of the SAME logical record stream
 * {key, amount, note}, consumed by the SAME task kernel
 * (acc[key] += amount; checksum ^= fnv1a(note bytes)), answers
 * asserted identical:
 *
 *   raw  — contiguous conventional records:
 *          [u8 key][u32 amount][u16 len][note bytes inline]
 *   am   — the real instruction grammar (LIT/COMP + LEB128, byte-
 *          compatible with the runtime): one COMP(concat) per record
 *          holding LIT(key), LIT(amount), and the note as either
 *          COMP(template-sid) — a reference into a resident template
 *          table (64 x 48 B ~ 3 KiB, L1-sized) — or LIT(inline bytes)
 *          when the note is unique.
 *
 * Recurrence ratio p (percent of notes drawn from the templates) is
 * the swept variable: at p=0 the am form is pure overhead (the honest
 * falsification case), at high p references replace streamed bytes.
 *
 * usage: membench raw|am <p 0..100> <n_records> <passes>
 * prints one JSON line with stream bytes, seconds (best pass), and the
 * task results (for cross-representation assertion).
 *
 * cc -O2 -o membench membench.c
 * Run under valgrind --tool=cachegrind for deterministic miss counts.
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define LIT 0x01
#define COMP 0x02
#define CONCAT 1
#define TMPL_BASE 100
#define N_TMPL 64
#define NOTE_LEN 48
#define N_KEYS 8

static uint8_t g_tmpl[N_TMPL][NOTE_LEN];

/* deterministic PRNG: the logical stream is identical in both modes */
static uint64_t g_rng = 0x243F6A8885A308D3ULL;
static uint64_t rnd(void) {
    g_rng ^= g_rng << 13;
    g_rng ^= g_rng >> 7;
    g_rng ^= g_rng << 17;
    return g_rng;
}

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void put_uv(uint8_t **w, uint64_t n) {
    do {
        uint8_t c = n & 0x7F;
        n >>= 7;
        if (n) c |= 0x80;
        *(*w)++ = c;
    } while (n);
}

static uint64_t get_uv(const uint8_t **r) {
    uint64_t n = 0;
    int shift = 0;
    for (;;) {
        uint8_t c = *(*r)++;
        n |= (uint64_t)(c & 0x7F) << shift;
        if (!(c & 0x80)) return n;
        shift += 7;
    }
}

static uint64_t fnv1a(const uint8_t *p, size_t n, uint64_t h) {
    for (size_t i = 0; i < n; i++) {
        h ^= p[i];
        h *= 0x100000001B3ULL;
    }
    return h;
}

static uint64_t xor64(const uint8_t *p, size_t n) {
    uint64_t h = 0, x;
    for (size_t i = 0; i + 8 <= n; i += 8) {
        memcpy(&x, p + i, 8);
        h ^= x;
    }
    return h;
}

int main(int argc, char **argv) {
    if (argc != 5 && argc != 6) {
        fprintf(stderr, "usage: membench raw|am <p> <n> <passes> [light]\n");
        return 1;
    }
    int light = argc == 6;   /* light kernel: memory-dominant (8B xor loads) */
    int is_am = !strcmp(argv[1], "am");
    int p = atoi(argv[2]);
    long n = atol(argv[3]);
    int passes = atoi(argv[4]);

    for (int t = 0; t < N_TMPL; t++)
        for (int i = 0; i < NOTE_LEN; i++)
            g_tmpl[t][i] = (uint8_t)rnd();

    /* generate the stream; the draw sequence is mode-independent */
    size_t cap = (size_t)n * (NOTE_LEN + 24);
    uint8_t *buf = malloc(cap);
    if (!buf) { fprintf(stderr, "oom\n"); return 1; }
    uint8_t *w = buf;
    uint8_t note[NOTE_LEN];
    for (long i = 0; i < n; i++) {
        uint8_t key = rnd() % N_KEYS;
        uint32_t amount = rnd() % 10000;
        int recurring = (int)(rnd() % 100) < p;
        int tmpl = rnd() % N_TMPL;
        if (!recurring)
            for (int b = 0; b < NOTE_LEN; b++) note[b] = (uint8_t)rnd();
        if (!is_am) {
            *w++ = key;
            memcpy(w, &amount, 4); w += 4;
            uint16_t len = NOTE_LEN;
            memcpy(w, &len, 2); w += 2;
            memcpy(w, recurring ? g_tmpl[tmpl] : note, NOTE_LEN);
            w += NOTE_LEN;
        } else {
            *w++ = COMP; put_uv(&w, CONCAT); put_uv(&w, 3);
            *w++ = LIT; put_uv(&w, 1); *w++ = key;
            *w++ = LIT; put_uv(&w, 4); memcpy(w, &amount, 4); w += 4;
            if (recurring) {
                *w++ = COMP; put_uv(&w, TMPL_BASE + tmpl); put_uv(&w, 0);
            } else {
                *w++ = LIT; put_uv(&w, NOTE_LEN);
                memcpy(w, note, NOTE_LEN); w += NOTE_LEN;
            }
        }
    }
    size_t stream = (size_t)(w - buf);

    /* the task kernel: same computation, different representation walk */
    uint64_t sums[N_KEYS];
    uint64_t checksum = 0;
    double best = 1e18;
    for (int pass = 0; pass < passes; pass++) {
        memset(sums, 0, sizeof sums);
        checksum = 0;
        double t0 = now();
        const uint8_t *r = buf;
        const uint8_t *end = buf + stream;
        if (!is_am) {
            while (r < end) {
                uint8_t key = *r++;
                uint32_t amount;
                memcpy(&amount, r, 4); r += 4;
                uint16_t len;
                memcpy(&len, r, 2); r += 2;
                sums[key] += amount;
                checksum ^= light ? xor64(r, len)
                                  : fnv1a(r, len, 0xcbf29ce484222325ULL);
                r += len;
            }
        } else {
            while (r < end) {
                r++; get_uv(&r); get_uv(&r);      /* COMP concat argc=3 */
                r++; get_uv(&r);                   /* LIT 1 */
                uint8_t key = *r++;
                r++; get_uv(&r);                   /* LIT 4 */
                uint32_t amount;
                memcpy(&amount, r, 4); r += 4;
                sums[key] += amount;
                uint8_t tag = *r++;
                if (tag == COMP) {                 /* resident template ref */
                    uint64_t sid = get_uv(&r); get_uv(&r);
                    checksum ^= light
                        ? xor64(g_tmpl[sid - TMPL_BASE], NOTE_LEN)
                        : fnv1a(g_tmpl[sid - TMPL_BASE], NOTE_LEN,
                                0xcbf29ce484222325ULL);
                } else {                           /* unique note inline */
                    uint64_t len = get_uv(&r);
                    checksum ^= light ? xor64(r, len)
                                      : fnv1a(r, len, 0xcbf29ce484222325ULL);
                    r += len;
                }
            }
        }
        double dt = now() - t0;
        if (dt < best) best = dt;
    }

    uint64_t total = 0;
    for (int k = 0; k < N_KEYS; k++) total += sums[k];
    printf("{\"mode\": \"%s\", \"p\": %d, \"records\": %ld, "
           "\"stream_bytes\": %zu, \"seconds\": %.4f, "
           "\"sum\": %llu, \"checksum\": %llu}\n",
           argv[1], p, n, stream, best,
           (unsigned long long)total, (unsigned long long)checksum);
    free(buf);
    return 0;
}
