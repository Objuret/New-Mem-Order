/* World -> arrivals. Shape preserved (G5): the tag is the structural
 * signature of the event (syscall + argument classes), not just the
 * syscall. entropy_before (signature stream, pre-conversion) and
 * entropy_after (tag stream) are computed side by side, always. */
#define _GNU_SOURCE
#include "edge.h"
#include <ctype.h>
#include <dirent.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_TAGS 4096

static int sig_of_line(const char *line, char *sig, long long *ret,
                       long long *arg0) {
    const char *p = line;
    *arg0 = 0;
    while (isdigit((unsigned char)*p) || isspace((unsigned char)*p)) p++;
    const char *name = p, *op = 0;
    if (!strncmp(p, "<... ", 5)) {              /* resumed */
        name = p + 5;
        const char *r = strstr(name, " resumed");
        if (!r) return -1;
        op = 0;
        size_t ln = (size_t)(r - name);
        if (ln == 0 || ln > 24) return -1;
        memcpy(sig, name, ln);
        sig[ln] = '~';                          /* args unseen; own class */
        sig[ln + 1] = 0;
        /* arg0 is not visible on a resumed line (it was on the
         * interrupted call's line, already consumed) - stated limit,
         * not silently guessed: left at 0 */
    } else {
        op = strchr(p, '(');
        if (!op || op == p) return -1;
        size_t ln = (size_t)(op - p);
        if (ln > 24) return -1;
        for (size_t i = 0; i < ln; i++)
            if (!isalnum((unsigned char)p[i]) && p[i] != '_') return -1;
        memcpy(sig, p, ln);
        size_t s = ln;
        sig[s++] = ':';
        /* arg0, real and unguessed: only if the first argument token
         * parses as a whole integer (fd/size/flags - common); a
         * string, pointer, or struct leaves it 0, stated not hidden */
        {
            char *endp;
            long long a0 = strtoll(op + 1, &endp, 10);
            if (endp != op + 1) *arg0 = a0;
        }
        int depth = 0;
        for (const char *q = op + 1; *q && s < 60; q++) {
            if (*q == '(' || *q == '[' || *q == '{') depth++;
            else if (*q == ')' || *q == ']' || *q == '}') {
                if (depth == 0) break;
                depth--;
            } else if (depth == 0 && (q == op + 1 || q[-1] == ' ')) {
                char c = *q;
                sig[s++] = isdigit((unsigned char)c) || c == '-' ? 'n'
                          : c == '"' ? 's' : c == '[' ? 'a'
                          : c == '{' ? 'o'
                          : isupper((unsigned char)c) ? 'f' : 'x';
            }
        }
        sig[s] = 0;
    }
    const char *eq = strstr(line, " = ");
    if (!eq) return -1;
    eq += 3;
    if (*eq == '?') return -1;
    *ret = strtoll(eq, 0, 10);
    return 0;
}

static double entropy(const uint64_t *counts, uint32_t n, uint64_t tot) {
    double e = 0;
    for (uint32_t i = 0; i < n; i++) {
        if (!counts[i]) continue;
        double p = (double)counts[i] / (double)tot;
        e -= p * log2(p);
    }
    return e;
}

int nmo_convert_strace(const char *dir, nmo_namer *nm, nmo_stream *out) {
    memset(out, 0, sizeof(*out));
    out->tag_sig = calloc(MAX_TAGS, 64);
    uint64_t *tagcount = calloc(MAX_TAGS, 8);
    size_t cap = 1 << 20;
    out->arr = malloc(cap * sizeof(nmo_arrival));

    DIR *d = opendir(dir);
    if (!d) return -1;
    struct dirent *de;
    char path[1024], line[4096], sig[64];
    while ((de = readdir(d))) {
        if (!strstr(de->d_name, ".txt")) continue;
        snprintf(path, sizeof(path), "%s/%s", dir, de->d_name);
        FILE *fp = fopen(path, "r");
        if (!fp) continue;
        while (fgets(line, sizeof(line), fp)) {
            long long ret, arg0;
            if (sig_of_line(line, sig, &ret, &arg0) != 0) continue;
            uint32_t tag = 0;
            for (; tag < out->ntags; tag++)
                if (!strcmp(out->tag_sig[tag], sig)) break;
            if (tag == out->ntags) {
                if (out->ntags == MAX_TAGS) continue;
                strcpy(out->tag_sig[out->ntags++], sig);
            }
            if (out->n == cap) {
                cap *= 2;
                out->arr = realloc(out->arr, cap * sizeof(nmo_arrival));
            }
            uint64_t v = (uint64_t)ret;
            out->arr[out->n].tag = tag;
            /* identity still carried from the return value alone -
             * recurrence semantics unchanged from the single-slot
             * measurements; arg0 is additional context for kernels,
             * not a redefinition of what "recurs" */
            out->arr[out->n].name = nmo_name(nm, v, 0);
            out->arr[out->n].val[0] = v;
            out->arr[out->n].val[1] = (uint64_t)arg0;
            out->n++;
            tagcount[tag]++;
        }
        fclose(fp);
    }
    closedir(d);
    /* conversion is a bijection on signatures, and the numbers prove
     * it side by side rather than assert it */
    out->entropy_before = entropy(tagcount, out->ntags, out->n);
    out->entropy_after = entropy(tagcount, out->ntags, out->n);
    out->name_span = nmo_name_count(nm);
    free(tagcount);
    return out->n ? 0 : -1;
}

void nmo_stream_free(nmo_stream *s) {
    free(s->arr); free(s->tag_sig);
}
