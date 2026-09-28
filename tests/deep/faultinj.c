/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* faultinj.c — an LD_PRELOAD shim that makes the Nth call of one libc function fail.
 *
 * The question it answers: when the disk says no (ENOSPC, EIO, EMFILE) at ANY point of a run,
 * does bench fail closed — a nonzero exit, no torn evidence, a world the next run can use?
 * tests/deep/fault_sweep.py counts the calls of a clean run (FI_COUNT), then replays the run
 * once per (function, N), failing exactly that call, and audits the world after each.
 *
 *   FI_FN=rename FI_NTH=3 FI_ERRNO=5 LD_PRELOAD=tests/deep/faultinj.so supervisor/bench run s.ops
 *   FI_COUNT=/tmp/counts LD_PRELOAD=... supervisor/bench run s.ops      (writes "fn count" lines)
 *
 * Only the process named "bench" is touched: the helper and every worker pass straight through
 * (workers get a fixed env without LD_PRELOAD anyway), and a forked child before exec is not
 * the supervisor, so it is skipped by pid. Harness only; never linked into bench. */
#define _GNU_SOURCE
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

enum { F_OPEN, F_OPENAT, F_MKDIR, F_RENAME, F_LINK, F_WRITE, F_FOPEN, F_FCLOSE, F_OPENDIR, F_CHMOD,
       F_READ, F_UNLINK, F_RMDIR, F_N };
static const char *NAME[F_N] = {"open", "openat", "mkdir", "rename", "link", "write", "fopen",
                                "fclose", "opendir", "chmod", "read", "unlink", "rmdir"};
static unsigned long counts[F_N];
static int target = -1, active, err = EIO;
static unsigned long nth;
static pid_t me;
static const char *count_path;

__attribute__((constructor)) static void fi_init(void) {
    if (strcmp(program_invocation_short_name, "bench") != 0) return;
    me = getpid();
    active = 1;
    const char *fn = getenv("FI_FN"), *n = getenv("FI_NTH"), *e = getenv("FI_ERRNO");
    count_path = getenv("FI_COUNT");
    if (fn && n) {
        for (int i = 0; i < F_N; i++) if (!strcmp(fn, NAME[i])) target = i;
        nth = strtoul(n, NULL, 10);
    }
    if (e) err = atoi(e);
}

__attribute__((destructor)) static void fi_fini(void) {
    if (!active || !count_path || getpid() != me) return;
    int fd = (int)syscall(257 /* openat */, AT_FDCWD, count_path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
    if (fd < 0) return;
    char line[64];
    for (int i = 0; i < F_N; i++) {
        int l = snprintf(line, sizeof line, "%s %lu\n", NAME[i], counts[i]);
        if (syscall(1 /* write */, fd, line, (size_t)l) < 0) break;
    }
    close(fd);
}

/* 1: this call fails. counts only the supervisor's own calls. */
static int hit(int f) {
    if (!active || getpid() != me) return 0;
    unsigned long c = ++counts[f];
    if (f == target && c == nth) { errno = err; return 1; }
    return 0;
}

#define REAL(ret, name, ...) static ret (*real)(__VA_ARGS__); if (!real) real = dlsym(RTLD_NEXT, name)

int open(const char *p, int flags, ...) {
    REAL(int, "open", const char *, int, ...);
    mode_t m = 0;
    if (flags & (O_CREAT | O_TMPFILE)) { va_list ap; va_start(ap, flags); m = va_arg(ap, mode_t); va_end(ap); }
    if (hit(F_OPEN)) return -1;
    return real(p, flags, m);
}
int open64(const char *p, int flags, ...) __attribute__((alias("open")));

int openat(int d, const char *p, int flags, ...) {
    REAL(int, "openat", int, const char *, int, ...);
    mode_t m = 0;
    if (flags & (O_CREAT | O_TMPFILE)) { va_list ap; va_start(ap, flags); m = va_arg(ap, mode_t); va_end(ap); }
    if (hit(F_OPENAT)) return -1;
    return real(d, p, flags, m);
}
int openat64(int d, const char *p, int flags, ...) __attribute__((alias("openat")));

int mkdir(const char *p, mode_t m) { REAL(int, "mkdir", const char *, mode_t); return hit(F_MKDIR) ? -1 : real(p, m); }
int rename(const char *a, const char *b) { REAL(int, "rename", const char *, const char *); return hit(F_RENAME) ? -1 : real(a, b); }
int link(const char *a, const char *b) { REAL(int, "link", const char *, const char *); return hit(F_LINK) ? -1 : real(a, b); }
ssize_t write(int fd, const void *b, size_t n) { REAL(ssize_t, "write", int, const void *, size_t); return hit(F_WRITE) ? -1 : real(fd, b, n); }
ssize_t read(int fd, void *b, size_t n) { REAL(ssize_t, "read", int, void *, size_t); return hit(F_READ) ? -1 : real(fd, b, n); }
int unlink(const char *p) { REAL(int, "unlink", const char *); return hit(F_UNLINK) ? -1 : real(p); }
int rmdir(const char *p) { REAL(int, "rmdir", const char *); return hit(F_RMDIR) ? -1 : real(p); }
int chmod(const char *p, mode_t m) { REAL(int, "chmod", const char *, mode_t); return hit(F_CHMOD) ? -1 : real(p, m); }
FILE *fopen(const char *p, const char *m) { REAL(FILE *, "fopen", const char *, const char *); return hit(F_FOPEN) ? NULL : real(p, m); }
FILE *fopen64(const char *p, const char *m) __attribute__((alias("fopen")));
DIR *opendir(const char *p) { REAL(DIR *, "opendir", const char *); return hit(F_OPENDIR) ? NULL : real(p); }

/* a failed fclose still closes (POSIX leaves the stream unusable either way): the data is lost,
   which is exactly what ENOSPC at flush time looks like. */
int fclose(FILE *f) {
    REAL(int, "fclose", FILE *);
    int fail = hit(F_FCLOSE);
    int r = real(f);
    if (fail) { errno = err; return EOF; }
    return r;
}
