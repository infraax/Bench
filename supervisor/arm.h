/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* arm.h — the owner's token. one answer, shared by bench and bench-helper. */
#ifndef ARM_H
#define ARM_H
#include <stddef.h>
#include <sys/types.h>
#include <time.h>

#define TOKEN_REL "sessions/OWNER_TOKEN"

/* which file armed the run, and which file it was: (dev, ino, mtime) pinned at arm. */
typedef struct {
    int             present;   /* 1 = a valid token was found */
    dev_t           dev;
    ino_t           ino;
    struct timespec mtime;
    char            path[1024];
} TokenId;

/* the token rule, v0. BENCH_TOKEN (if set, non-empty) is tried first, then
   <root>/sessions/OWNER_TOKEN. a token is valid iff it is a regular file (not a link),
   owned by the uid running bench, and not group- or world-writable. content is not read.
   returns 1 valid (t filled), 0 not armed (why says which rule failed). */
int token_read(const char *root, const char *env_token, TokenId *t, char *why, size_t whyn);

/* same file, untouched since it was pinned. */
int token_same(const TokenId *a, const TokenId *b);

/* token_read without the details. */
int owner_token_present(const char *root, const char *env_token);

#endif
