/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* sha256.c — FIPS 180-4. public domain. small, correct, no deps.
 * verified against python hashlib and the tools/hash.py tree scheme. */
#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "sha256.h"

static const uint32_t K[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
};

#define ROR(x,n) (((x)>>(n))|((x)<<(32-(n))))

static void block(Sha256 *c, const uint8_t *p) {
    uint32_t w[64], a,b,cc,d,e,f,g,h;
    for (int i = 0; i < 16; i++)
        w[i] = (uint32_t)p[i*4]<<24 | (uint32_t)p[i*4+1]<<16 | (uint32_t)p[i*4+2]<<8 | p[i*4+3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ROR(w[i-15],7)^ROR(w[i-15],18)^(w[i-15]>>3);
        uint32_t s1 = ROR(w[i-2],17)^ROR(w[i-2],19)^(w[i-2]>>10);
        w[i] = w[i-16]+s0+w[i-7]+s1;
    }
    a=c->state[0];b=c->state[1];cc=c->state[2];d=c->state[3];
    e=c->state[4];f=c->state[5];g=c->state[6];h=c->state[7];
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = ROR(e,6)^ROR(e,11)^ROR(e,25);
        uint32_t ch = (e&f)^(~e&g);
        uint32_t t1 = h+S1+ch+K[i]+w[i];
        uint32_t S0 = ROR(a,2)^ROR(a,13)^ROR(a,22);
        uint32_t maj = (a&b)^(a&cc)^(b&cc);
        uint32_t t2 = S0+maj;
        h=g;g=f;f=e;e=d+t1;d=cc;cc=b;b=a;a=t1+t2;
    }
    c->state[0]+=a;c->state[1]+=b;c->state[2]+=cc;c->state[3]+=d;
    c->state[4]+=e;c->state[5]+=f;c->state[6]+=g;c->state[7]+=h;
}

void sha256_init(Sha256 *c) {
    static const uint32_t iv[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                                   0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    memcpy(c->state, iv, sizeof iv);
    c->nbits = 0; c->len = 0;
}

void sha256_update(Sha256 *c, const void *data, size_t n) {
    const uint8_t *p = data;
    c->nbits += (uint64_t)n * 8;
    while (n) {
        size_t take = 64 - c->len;
        if (take > n) take = n;
        memcpy(c->buf + c->len, p, take);
        c->len += take; p += take; n -= take;
        if (c->len == 64) { block(c, c->buf); c->len = 0; }
    }
}

void sha256_final(Sha256 *c, char hex[65]) {
    uint64_t bits = c->nbits;
    uint8_t pad = 0x80;
    sha256_update(c, &pad, 1);
    pad = 0;
    while (c->len != 56) sha256_update(c, &pad, 1);
    uint8_t be[8];
    for (int i = 0; i < 8; i++) be[i] = (uint8_t)(bits >> (56 - i*8));
    sha256_update(c, be, 8);
    static const char *hx = "0123456789abcdef";
    for (int i = 0; i < 8; i++)
        for (int j = 0; j < 4; j++) {
            uint8_t byte = (uint8_t)(c->state[i] >> (24 - j*8));
            hex[(i*4+j)*2]   = hx[byte >> 4];
            hex[(i*4+j)*2+1] = hx[byte & 15];
        }
    hex[64] = 0;
}

/* ---- tree hash, matching tools/hash.py ---- */

static int join(char *out, size_t n, const char *a, const char *b) {
    int w = snprintf(out, n, "%s/%s", a, b);
    return (w < 0 || (size_t)w >= n) ? -1 : 0;
}

/* collect regular non-symlink files under abs, recording relpath (relative to base_root). */
typedef struct { char **v; size_t n, cap; } List;

static int list_push(List *l, const char *s) {
    if (l->n == l->cap) {
        size_t cap = l->cap ? l->cap * 2 : 64;
        char **v = realloc(l->v, cap * sizeof *v);
        if (!v) return -1;
        l->v = v; l->cap = cap;
    }
    l->v[l->n] = strdup(s);
    return l->v[l->n++] ? 0 : -1;
}

static int cmp_str(const void *a, const void *b) {
    return strcmp(*(char *const *)a, *(char *const *)b);
}

static int walk(const char *abs, const char *rel, List *l) {
    DIR *d = opendir(abs);
    if (!d) return -1;
    int rc = 0;
    struct dirent *e;
    while (rc == 0 && (e = readdir(d)) != NULL) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        if (!strcmp(e->d_name, "__pycache__")) continue;   /* bytecode is derived, not board state */
        size_t nlen = strlen(e->d_name);
        if (nlen >= 4 && !strcmp(e->d_name + nlen - 4, ".pyc")) continue;
        char a2[2048], r2[2048];
        struct stat st;
        if (join(a2, sizeof a2, abs, e->d_name) || join(r2, sizeof r2, rel, e->d_name)) { rc = -1; break; }
        if (lstat(a2, &st) != 0) { rc = -1; break; }
        if (S_ISLNK(st.st_mode)) continue;        /* a symlink is not board state */
        if (S_ISREG(st.st_mode)) rc = list_push(l, r2);
        else if (S_ISDIR(st.st_mode)) rc = walk(a2, r2, l);
    }
    closedir(d);
    return rc;
}

static int hash_one_file(Sha256 *h, const char *abs, const char *rel) {
    FILE *f = fopen(abs, "rb");
    if (!f) return -1;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return -1; }
    long sz = ftell(f);
    if (sz < 0 || fseek(f, 0, SEEK_SET) != 0) { fclose(f); return -1; }
    char hdr[64];
    sha256_update(h, rel, strlen(rel));
    sha256_update(h, "\0", 1);
    int hl = snprintf(hdr, sizeof hdr, "%ld", sz);
    sha256_update(h, hdr, (size_t)hl);
    sha256_update(h, "\0", 1);
    char buf[8192];
    size_t r;
    int rc = 0;
    while ((r = fread(buf, 1, sizeof buf, f)) > 0) sha256_update(h, buf, r);
    if (ferror(f)) rc = -1;
    fclose(f);
    return rc;
}

int tree_hash(const char *root, const char *const *paths, int npaths, char hex[65]) {
    const char *roots[16];
    if (npaths < 0 || npaths > 16) return -1;
    for (int i = 0; i < npaths; i++) roots[i] = root;
    return tree_hash_roots(roots, paths, npaths, hex);
}

int tree_hash_roots(const char *const *roots, const char *const *paths, int npaths, char hex[65]) {
    Sha256 h;
    sha256_init(&h);
    for (int i = 0; i < npaths; i++) {
        const char *root = roots[i];
        char abs[2048];
        struct stat st;
        if (join(abs, sizeof abs, root, paths[i])) return -1;
        if (lstat(abs, &st) != 0) {
            sha256_update(&h, "missing\0", 8);
            sha256_update(&h, paths[i], strlen(paths[i]));
            sha256_update(&h, "\0", 1);
            continue;
        }
        if (S_ISREG(st.st_mode)) {
            if (hash_one_file(&h, abs, paths[i]) != 0) return -1;
            continue;
        }
        if (!S_ISDIR(st.st_mode)) continue;
        List l = {0};
        if (walk(abs, paths[i], &l) != 0) { for (size_t j=0;j<l.n;j++) free(l.v[j]); free(l.v); return -1; }
        qsort(l.v, l.n, sizeof *l.v, cmp_str);
        int rc = 0;
        for (size_t j = 0; j < l.n && rc == 0; j++) {
            char abs2[2048];
            if (join(abs2, sizeof abs2, root, l.v[j])) rc = -1;
            else rc = hash_one_file(&h, abs2, l.v[j]);
        }
        for (size_t j = 0; j < l.n; j++) free(l.v[j]);
        free(l.v);
        if (rc != 0) return -1;
    }
    sha256_final(&h, hex);
    return 0;
}
