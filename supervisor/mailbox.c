/* mailbox.c — start the helper and talk to it. unix socket, this machine only, no opcode.
 *
 * order matters: bench binds, listens and connects BEFORE the helper exists, so the first
 * (and only) connection the helper accepts is bench's own. the path is then unlinked. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "mailbox.h"

#define T_OPEN_MS 2000   /* helper boot + first PING */
#define T_ASK_MS  500    /* one answer. counted in T_frame by the gate. */

static int helper_path(char *out, size_t n) {
    char self[PATH_MAX];
    ssize_t l = readlink("/proc/self/exe", self, sizeof self - 1);
    if (l <= 0) return -1;
    self[l] = 0;
    char *slash = strrchr(self, '/');
    if (!slash) return -1;
    *slash = 0;
    return snprintf(out, n, "%s/bench-helper", self) >= (int)n ? -1 : 0;
}

static void reap(pid_t pid) {
    for (int i = 0; i < 100; i++) {           /* up to 1 s for a clean exit */
        if (waitpid(pid, NULL, WNOHANG) == pid) return;
        struct timespec ts = {0, 10000000};
        nanosleep(&ts, NULL);
    }
    kill(pid, SIGKILL);
    waitpid(pid, NULL, 0);
}

int mb_open(Mailbox *m, const char *dir, const char *root, int log_fd, char *why, size_t whyn) {
    m->fd = -1;
    m->pid = -1;
    m->log_fd = log_fd;
    char exe[PATH_MAX];
    if (helper_path(exe, sizeof exe) != 0 || access(exe, X_OK) != 0) {
        snprintf(why, whyn, "helper missing (bench-helper next to bench)");
        return -1;
    }
    struct sockaddr_un a;
    memset(&a, 0, sizeof a);
    a.sun_family = AF_UNIX;
    if (snprintf(a.sun_path, sizeof a.sun_path, "%s/helper.sock", dir) >= (int)sizeof a.sun_path) {
        snprintf(why, whyn, "mailbox path longer than %zu bytes", sizeof a.sun_path - 1);
        return -1;
    }
    int lfd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    int cfd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (lfd < 0 || cfd < 0 || bind(lfd, (struct sockaddr *)&a, sizeof a) != 0 || listen(lfd, 1) != 0 ||
        connect(cfd, (struct sockaddr *)&a, sizeof a) != 0) {
        snprintf(why, whyn, "mailbox socket: %s", strerror(errno));
        if (lfd >= 0) close(lfd);
        if (cfd >= 0) close(cfd);
        unlink(a.sun_path);
        return -1;
    }
    unlink(a.sun_path);                        /* paired in the backlog; nobody else finds it */

    const char *tok = getenv("BENCH_TOKEN");
    char envtok[PATH_MAX + 16];
    char *env[2] = {NULL, NULL};
    if (tok && *tok && snprintf(envtok, sizeof envtok, "BENCH_TOKEN=%s", tok) < (int)sizeof envtok)
        env[0] = envtok;
    char fdarg[16];
    snprintf(fdarg, sizeof fdarg, "%d", lfd);

    pid_t pid = fork();
    if (pid < 0) {
        snprintf(why, whyn, "fork helper: %s", strerror(errno));
        close(lfd); close(cfd);
        return -1;
    }
    if (pid == 0) {
        fcntl(lfd, F_SETFD, 0);                /* the listener, and only it, crosses exec */
        char *argv[] = {exe, (char *)root, fdarg, NULL};
        execve(exe, argv, env);                /* env: BENCH_TOKEN only, if set */
        _exit(127);
    }
    close(lfd);
    m->fd = cfd;
    m->pid = pid;

    char r[128];
    int ok = mb_ask(m, "PING", NULL, r, sizeof r);
    if (ok != 1) {
        snprintf(why, whyn, "helper silent (no PING answer in %d ms)", T_OPEN_MS);
        mb_close(m);
        return -1;
    }
    return 0;
}

int mb_ask(Mailbox *m, const char *word, const char *arg, char *reply, size_t n) {
    reply[0] = 0;
    if (m->fd < 0) return -1;
    char q[96];
    int ql = snprintf(q, sizeof q, "%s%s%s\n", word, arg ? " " : "", arg ? arg : "");
    if (ql < 0 || ql >= (int)sizeof q || send(m->fd, q, (size_t)ql, MSG_NOSIGNAL) != ql) return -1;

    char buf[128];
    size_t used = 0;
    int budget = !strcmp(word, "PING") ? T_OPEN_MS : T_ASK_MS;
    for (;;) {
        struct pollfd p = {m->fd, POLLIN, 0};
        int pr = poll(&p, 1, budget);
        if (pr < 0 && errno == EINTR) continue;
        if (pr <= 0) return -1;
        ssize_t r = read(m->fd, buf + used, 1);
        if (r <= 0) return -1;
        if (buf[used] == '\n') break;
        if (++used >= sizeof buf - 1) return -1;
    }
    buf[used] = 0;
    if (m->log_fd >= 0) dprintf(m->log_fd, "MAILBOX %.*s -> %s\n", ql - 1, q, buf);

    /* "<WORD> yes|no <reason>": the word must echo the question, or the line is broken */
    size_t wl = strlen(word);
    if (strncmp(buf, word, wl) != 0 || buf[wl] != ' ') return -1;
    const char *v = buf + wl + 1;
    int yes = !strncmp(v, "yes ", 4), no = !strncmp(v, "no ", 3);
    if (!yes && !no) return -1;
    snprintf(reply, n, "%s", v + (yes ? 4 : 3));
    return yes;
}

void mb_close(Mailbox *m) {
    if (m->fd >= 0) close(m->fd);
    m->fd = -1;
    if (m->pid > 0) reap(m->pid);
    m->pid = -1;
}
