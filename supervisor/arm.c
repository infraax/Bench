/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* arm.c — the owner's token, v0: a file the owner made. a later hardware key replaces this file. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "arm.h"

static int check(const char *p, TokenId *t, char *why, size_t whyn) {
    struct stat st;
    if (lstat(p, &st) != 0) { snprintf(why, whyn, "no token at %.200s", p); return 0; }
    if (!S_ISREG(st.st_mode)) { snprintf(why, whyn, "token %.200s is not a regular file", p); return 0; }
    if (st.st_uid != getuid()) { snprintf(why, whyn, "token %.200s is not owned by this user", p); return 0; }
    if (st.st_mode & (S_IWGRP | S_IWOTH)) {
        snprintf(why, whyn, "token %.200s is group- or world-writable", p);
        return 0;
    }
    t->present = 1;
    t->dev = st.st_dev;
    t->ino = st.st_ino;
    t->mtime = st.st_mtim;
    snprintf(t->path, sizeof t->path, "%s", p);
    return 1;
}

int token_read(const char *root, const char *env_token, TokenId *t, char *why, size_t whyn) {
    memset(t, 0, sizeof *t);
    char w[160] = "";
    if (env_token && *env_token && check(env_token, t, w, sizeof w)) return 1;
    char p[1024];
    int n = snprintf(p, sizeof p, "%s/%s", root, TOKEN_REL);
    if (n > 0 && (size_t)n < sizeof p && check(p, t, why, whyn)) return 1;
    if (w[0]) snprintf(why, whyn, "%s", w);   /* the env token's reason, if the owner set one */
    return 0;
}

int token_same(const TokenId *a, const TokenId *b) {
    return a->present && b->present && a->dev == b->dev && a->ino == b->ino &&
           a->mtime.tv_sec == b->mtime.tv_sec && a->mtime.tv_nsec == b->mtime.tv_nsec &&
           !strcmp(a->path, b->path);
}

int owner_token_present(const char *root, const char *env_token) {
    TokenId t;
    char why[256];
    return token_read(root, env_token, &t, why, sizeof why);
}
