/* arm.c — the owner's token, v0: a file that exists. a later hardware key replaces this file. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <sys/stat.h>
#include "arm.h"

static int is_file(const char *p) {
    struct stat st;
    return stat(p, &st) == 0 && S_ISREG(st.st_mode);
}

int owner_token_present(const char *root, const char *env_token) {
    if (env_token && *env_token && is_file(env_token)) return 1;
    char p[1024];
    int w = snprintf(p, sizeof p, "%s/%s", root, TOKEN_REL);
    return w > 0 && (size_t)w < sizeof p && is_file(p);
}
