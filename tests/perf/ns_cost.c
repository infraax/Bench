/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* ns_cost.c — per-child start-up cost of the tool jail. built and run by `make perf`.
 * in a scratch world (cwd), times fork -> [setup] -> exec, wait, for:
 *   bare   no jail
 *   ns     sandbox_world_only() (the namespace view)
 *   full   sandbox_apply(JAIL_FULL): namespaces + landlock + seccomp, what EXEC gets
 * for /bin/true (setup cost alone) and python3 -c pass (what a tool pays in practice).
 * prints median microseconds per child. */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>
#include "sandbox.h"

static uint64_t now_us(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000u + (uint64_t)t.tv_nsec / 1000u;
}

static int cmp(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return x < y ? -1 : x > y;
}

static uint64_t one(int mode, char *const argv[]) {
    uint64_t t0 = now_us();
    pid_t pid = fork();
    if (pid == 0) {
        if (mode == 1 && sandbox_world_only() != 0) _exit(125);
        if (mode == 2 && sandbox_apply(JAIL_FULL) != 0) _exit(125);
        execv(argv[0], argv);
        _exit(127);
    }
    int st;
    waitpid(pid, &st, 0);
    if (!WIFEXITED(st) || WEXITSTATUS(st) != 0) { fprintf(stderr, "ns_cost: child failed (mode %d)\n", mode); exit(1); }
    return now_us() - t0;
}

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 50;
    if (n < 1 || n > 10000) return 2;
    char *truth[] = {"/bin/true", NULL}, *py[] = {"/usr/bin/python3", "-S", "-c", "pass", NULL};
    char *const *progs[] = {truth, py};
    const char *pname[] = {"true", "python3"}, *mname[] = {"bare", "ns", "full"};
    uint64_t *v = calloc((size_t)n, sizeof *v), med[2][3];
    if (!v) return 1;
    for (int p = 0; p < 2; p++)
        for (int m = 0; m < 3; m++) {
            for (int i = 0; i < n; i++) v[i] = one(m, progs[p]);
            qsort(v, (size_t)n, sizeof *v, cmp);
            med[p][m] = v[n / 2];
        }
    for (int p = 0; p < 2; p++)
        printf("child %-8s bare=%lluus ns=%lluus full=%lluus  ns_added=%lldus full_added=%lldus (median of %d)\n",
               pname[p], (unsigned long long)med[p][0], (unsigned long long)med[p][1], (unsigned long long)med[p][2],
               (long long)med[p][1] - (long long)med[p][0], (long long)med[p][2] - (long long)med[p][0], n);
    (void)mname;
    free(v);
    return 0;
}
