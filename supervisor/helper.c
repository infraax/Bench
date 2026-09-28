/* helper.c — bench-helper: the supervisor's mailbox on this machine. three words, one reason.
 *
 *   bench-helper <root> <listen-fd>
 *
 * started by bench only, with a listening unix socket bench created under sessions/<id>/.
 * accepts exactly one connection, and only from its parent (SO_PEERCRED), then closes the
 * listener: nobody else gets a line. requests, one per line:
 *
 *   PING            -> PING yes <reason>
 *   ARM_OK          -> ARM_OK yes|no <reason>      is the owner's token present?
 *   FRAME_OK <n>    -> FRAME_OK yes|no <reason>    may frame n run?
 *
 * anything else closes the line (no fourth word). EOF from bench: exit 0.
 * the helper can refuse; it cannot arm on its own — bench checks the token too.
 * v0 holds no key and no firmware. a later hardware key answers ARM_OK here instead. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
#include "arm.h"

#define LINE 128

static int reply(int fd, const char *word, int yes, const char *reason) {
    char out[LINE];
    int n = snprintf(out, sizeof out, "%s %s %s\n", word, yes ? "yes" : "no", reason);
    if (n < 0 || n >= (int)sizeof out) return -1;
    return send(fd, out, (size_t)n, MSG_NOSIGNAL) == n ? 0 : -1;
}

/* one line, at most LINE-1 bytes, without the newline. 0 ok, -1 EOF/error/too long. */
static int read_line(int fd, char *buf) {
    size_t used = 0;
    for (;;) {
        char c;
        ssize_t r = read(fd, &c, 1);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return -1;
        if (c == '\n') { buf[used] = 0; return 0; }
        if (used + 1 >= LINE) return -1;
        buf[used++] = c;
    }
}

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: bench-helper <root> <listen-fd>\n"); return 2; }
    const char *root = argv[1];
    char *end;
    long lfd = strtol(argv[2], &end, 10);
    if (*end || lfd < 0) return 2;

    int fd = accept((int)lfd, NULL, NULL);
    close((int)lfd);                       /* one connection, ever */
    if (fd < 0) return 1;
    struct ucred cr;
    socklen_t cl = sizeof cr;
    if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cr, &cl) != 0 || cr.pid != getppid()) {
        close(fd);                         /* only the process that started us gets a line */
        return 1;
    }

    const char *env_token = getenv("BENCH_TOKEN");
    char line[LINE];
    while (read_line(fd, line) == 0) {
        int armed = owner_token_present(root, env_token);
        int rc;
        if (!strcmp(line, "PING")) {
            rc = reply(fd, "PING", 1, "helper v0");   /* bench pins this: mailbox.h HELPER_VERSION */
        } else if (!strcmp(line, "ARM_OK")) {
            rc = reply(fd, "ARM_OK", armed, armed ? "owner token present" : "owner token absent");
        } else if (!strncmp(line, "FRAME_OK ", 9) && line[9]) {
            char why[64];
            snprintf(why, sizeof why, "%s n=%.20s", armed ? "armed" : "owner token absent", line + 9);
            rc = reply(fd, "FRAME_OK", armed, why);
        } else {
            rc = -1;                       /* not one of the three words: the line closes */
        }
        if (rc != 0) { close(fd); return 1; }
    }
    close(fd);
    return 0;
}
