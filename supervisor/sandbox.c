/* sandbox.c — seccomp-bpf + landlock + env scrub, applied in the tool child.
 * see sandbox.h for the honest limits. */
#define _GNU_SOURCE
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/landlock.h>
#include "sandbox.h"

extern char **environ;

/* ---- env scrub ---- */

char **tool_env(void) {
    static const char *keep_pfx[] = {"LANG=", "LC_", "TZ="};
    /* start with the fixed floor, then copy through a short allowlist of harmless vars. */
    size_t cap = 8;
    for (char **e = environ; *e; e++) cap++;
    char **out = calloc(cap, sizeof *out);
    if (!out) return NULL;
    size_t n = 0;
    out[n++] = strdup("PATH=/usr/bin:/bin");
    out[n++] = strdup("PYTHONDONTWRITEBYTECODE=1");   /* no __pycache__ under a write-jail */
    out[n++] = strdup("PYTHONNOUSERSITE=1");
    out[n++] = strdup("PYTHONHASHSEED=0");            /* determinism is the caller's problem; help it */
    for (char **e = environ; *e; e++) {
        for (size_t i = 0; i < sizeof keep_pfx / sizeof *keep_pfx; i++)
            if (strncmp(*e, keep_pfx[i], strlen(keep_pfx[i])) == 0) { out[n++] = strdup(*e); break; }
    }
    out[n] = NULL;
    for (size_t i = 0; i < n; i++) if (!out[i]) { free(out); return NULL; }
    return out;
}

/* ---- seccomp: KILL a named set of ambient-authority syscalls ---- */

static int seccomp_deny_ambient(void) {
    /* the antenna: EPERM, not KILL. CPython's own startup touches socket() in this
       environment, so a leash that kills the interpreter at boot is a liturgy, not a leash.
       A tool that genuinely reaches the antenna gets EPERM, raises, exits non-zero → fault. */
    static const int deny_errno[] = {
#ifdef __NR_socket
        __NR_socket,
#endif
#ifdef __NR_socketcall
        __NR_socketcall,
#endif
        __NR_connect, __NR_bind, __NR_listen, __NR_accept, __NR_accept4,
        __NR_sendto, __NR_recvfrom, __NR_sendmsg, __NR_recvmsg, __NR_socketpair,
        __NR_setsockopt, __NR_getsockopt,
    };
    /* the debugger, namespaces, mount, the key ring, io_uring: never innocent, never touched at
       startup. KILL — a real attempt dies with SIGSYS, which the supervisor sees as a fault. */
    static const int deny_kill[] = {
        __NR_ptrace, __NR_process_vm_readv, __NR_process_vm_writev,
        __NR_mount, __NR_umount2, __NR_pivot_root, __NR_chroot,
        __NR_unshare, __NR_setns,
        __NR_add_key, __NR_request_key, __NR_keyctl,
        /* io_uring: a ring does reads, writes, connects and opens the kernel never shows this
           filter one syscall at a time — a door past every rule above. CPython never touches it
           at startup. (codex's linux sandbox denies the same three.) */
#ifdef __NR_io_uring_setup
        __NR_io_uring_setup, __NR_io_uring_enter, __NR_io_uring_register,
#endif
    };
    size_t nk = sizeof deny_kill / sizeof deny_kill[0];
    size_t ne = sizeof deny_errno / sizeof deny_errno[0];

    const uint32_t ERRNO = SECCOMP_RET_ERRNO | (EPERM & SECCOMP_RET_DATA);
    size_t len = nk + ne + 8;   /* ld-arch, jeq, kill, ld-nr, compares, allow, kill, errno */
    struct sock_filter *f = calloc(len, sizeof *f);
    if (!f) return -1;
    size_t i = 0;
    f[i++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch));
    f[i++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0);
    f[i++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS);
    f[i++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr));
    /* tail after all compares: ALLOW at A, KILL at A+1, ERRNO at A+2. */
    size_t a = i + nk + ne;
    for (size_t j = 0; j < nk; j++) {
        uint8_t to = (uint8_t)((a + 1) - (i + 1));   /* -> KILL */
        f[i] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)deny_kill[j], to, 0);
        i++;
    }
    for (size_t j = 0; j < ne; j++) {
        uint8_t to = (uint8_t)((a + 2) - (i + 1));   /* -> ERRNO */
        f[i] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)deny_errno[j], to, 0);
        i++;
    }
    f[i++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW);
    f[i++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS);
    f[i++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, ERRNO);

    struct sock_fprog prog = { .len = (unsigned short)i, .filter = f };
    int rc = -1;
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0 &&
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog, 0, 0) == 0)
        rc = 0;
    free(f);
    return rc;
}

/* ---- landlock: write only under hold/ and proposed/, read everywhere ---- */

static int ll_add_path(int fd, const char *path, uint64_t allowed) {
    int p = open(path, O_PATH | O_CLOEXEC);
    if (p < 0) return errno == ENOENT ? 0 : -1;   /* proposed/ may not exist yet: nothing to grant */
    struct landlock_path_beneath_attr pb = { .allowed_access = allowed, .parent_fd = p };
    int rc = (int)syscall(__NR_landlock_add_rule, fd, LANDLOCK_RULE_PATH_BENEATH, &pb, 0);
    close(p);
    return rc;
}

static int landlock_write_jail(void) {
    /* handle only the write-ish accesses; read and execute stay unrestricted so python
       can start and read the image. write is then granted ONLY under hold/ and proposed/. */
    uint64_t wr = LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_MAKE_REG |
                  LANDLOCK_ACCESS_FS_MAKE_DIR | LANDLOCK_ACCESS_FS_REMOVE_FILE |
                  LANDLOCK_ACCESS_FS_REMOVE_DIR | LANDLOCK_ACCESS_FS_MAKE_SYM |
                  LANDLOCK_ACCESS_FS_TRUNCATE;
    struct landlock_ruleset_attr attr = { .handled_access_fs = wr };
    int rs = (int)syscall(__NR_landlock_create_ruleset, &attr, sizeof attr, 0);
    if (rs < 0) return -1;
    int rc = 0;
    if (ll_add_path(rs, "hold", wr) != 0) rc = -1;
    if (rc == 0 && ll_add_path(rs, "proposed", wr) != 0) rc = -1;
    if (rc == 0 && ll_add_path(rs, "tests/proposed", wr) != 0) rc = -1;
    if (rc == 0 && prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) rc = -1;
    if (rc == 0 && syscall(__NR_landlock_restrict_self, rs, 0) != 0) rc = -1;
    close(rs);
    return rc;
}

int sandbox_apply(Jail jail) {
    /* landlock first (needs open() on the tree), then seccomp which narrows syscalls. */
    if (jail == JAIL_FULL && landlock_write_jail() != 0) return -1;
    if (seccomp_deny_ambient() != 0) return -1;
    return 0;
}
