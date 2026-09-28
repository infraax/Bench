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
#include <limits.h>
#include <stdio.h>
#include <sched.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/landlock.h>
#include <linux/mount.h>
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
        /* the new mount API and file handles: inside its own mount namespace a root tool could
           clear read-only on the world view (mount_setattr) or open a file outside it by handle
           (open_by_handle_at). modules, kexec, bpf, perf, reboot, swap, port I/O: root-only
           doors no tool has business with. */
        __NR_open_by_handle_at,
#ifdef __NR_open_tree
        __NR_open_tree, __NR_move_mount, __NR_fsopen, __NR_fsconfig, __NR_fsmount, __NR_fspick,
#endif
#ifdef __NR_mount_setattr
        __NR_mount_setattr,
#endif
#ifdef __NR_open_tree_attr
        __NR_open_tree_attr,
#endif
        __NR_init_module, __NR_finit_module, __NR_delete_module, __NR_kexec_load,
#ifdef __NR_kexec_file_load
        __NR_kexec_file_load,
#endif
        __NR_bpf, __NR_perf_event_open, __NR_reboot, __NR_swapon, __NR_swapoff,
        __NR_iopl, __NR_ioperm,
    };
    size_t nk = sizeof deny_kill / sizeof deny_kill[0];
    size_t ne = sizeof deny_errno / sizeof deny_errno[0];

    const uint32_t ERRNO = SECCOMP_RET_ERRNO | (EPERM & SECCOMP_RET_DATA);
    size_t len = nk + ne + 9;   /* ld-arch, jeq, kill, ld-nr, x32, compares, allow, kill, errno */
    struct sock_filter *f = calloc(len, sizeof *f);
    if (!f) return -1;
    size_t i = 0;
    f[i++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch));
    f[i++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0);
    f[i++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS);
    f[i++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr));
    /* tail after all compares: ALLOW at A, KILL at A+1, ERRNO at A+2. */
    size_t a = i + 1 + nk + ne;
    /* x32: same AUDIT_ARCH_X86_64, but nr carries bit 30, so it would match none of the compares
       below and fall through to ALLOW. no tool here speaks x32: any such nr dies. */
    f[i] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, 0x40000000u, (uint8_t)((a + 1) - (i + 1)), 0);
    i++;
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

/* ---- namespaces: the tool child sees only the world ----
 * a private mount namespace (plus a user namespace when bench is not root, uid/gid mapped to
 * themselves) holding a fresh tmpfs root with, and only with:
 *   <world>            the world, read-only, at its own absolute path (cwd stays the same)
 *   <world>/hold, proposed, tests/proposed   read-write on top of it
 *   /usr (+ the /lib* /bin /sbin links or dirs, /etc/alternatives)   read-only: the interpreter
 *                      and its libraries
 *   /dev/null          the one device
 *   /tmp               a private tmpfs (the test runner's scratch), gone with the child
 * everything is nosuid; everything but /dev/null is nodev. the old root is detached after
 * pivot_root, so nothing outside is reachable by path; the fds a child holds are pipes, the
 * out file and /dev/null. sessions/ (snaps, token, logs) is read-only: the seal binds against
 * the tool even as root, and a TEST can no longer mint the token or move main/ or ROM.
 * seccomp (installed after this) kills mount, the new mount API, pivot_root, chroot, unshare,
 * setns and open_by_handle_at, so the child cannot undo any of it. any failure: -1, the child
 * does not run. */

static int sc_open_tree(const char *path) {
    return (int)syscall(__NR_open_tree, AT_FDCWD, path, OPEN_TREE_CLONE | OPEN_TREE_CLOEXEC | AT_RECURSIVE);
}

static int sc_setattr(int fd, const char *path, unsigned flags, uint64_t set) {
    struct mount_attr a = { .attr_set = set };
    return (int)syscall(__NR_mount_setattr, fd, path, flags, &a, sizeof a);
}

static int sc_move(int fd, const char *to) {
    return (int)syscall(__NR_move_mount, fd, "", AT_FDCWD, to, MOVE_MOUNT_F_EMPTY_PATH);
}

/* a detached, recursive clone of path with the given attributes. -2 if path is missing. */
static int clone_tree(const char *path, uint64_t attrs) {
    int fd = sc_open_tree(path);
    if (fd < 0) return errno == ENOENT ? -2 : -1;
    if (sc_setattr(fd, "", AT_EMPTY_PATH | AT_RECURSIVE, attrs) != 0) { close(fd); return -1; }
    return fd;
}

static int mkdir_p(const char *path) {
    char b[PATH_MAX];
    if (snprintf(b, sizeof b, "%s", path) >= (int)sizeof b) return -1;
    for (char *p = b + 1; *p; p++) {
        if (*p != '/') continue;
        *p = 0;
        if (mkdir(b, 0755) != 0 && errno != EEXIST) return -1;
        *p = '/';
    }
    return mkdir(b, 0755) != 0 && errno != EEXIST ? -1 : 0;
}

static int write_file(const char *path, const char *text) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t n = (ssize_t)strlen(text);
    int rc = write(fd, text, (size_t)n) == n ? 0 : -1;
    close(fd);
    return rc;
}

#define NS_STAGE "/tmp"   /* overmounted inside the private namespace only */
#ifndef MNT_DETACH
#define MNT_DETACH 2       /* <sys/mount.h>; not included: it clashes with <linux/mount.h> on some libcs */
#endif

int sandbox_world_only(void) {
    char w[PATH_MAX], at[PATH_MAX + 64];
    if (!getcwd(w, sizeof w) || w[0] != '/') return -1;
    uid_t uid = geteuid();
    gid_t gid = getegid();
    int flags = CLONE_NEWNS | CLONE_NEWIPC | (uid != 0 ? CLONE_NEWUSER : 0);
    if (unshare(flags) != 0) return -1;
    if (uid != 0) {
        char m[64];
        if (write_file("/proc/self/setgroups", "deny")) return -1;
        snprintf(m, sizeof m, "%u %u 1", (unsigned)uid, (unsigned)uid);
        if (write_file("/proc/self/uid_map", m)) return -1;
        snprintf(m, sizeof m, "%u %u 1", (unsigned)gid, (unsigned)gid);
        if (write_file("/proc/self/gid_map", m)) return -1;
    }
    if (syscall(__NR_mount, NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) != 0) return -1;

    /* clone everything first: the clones are detached, so overmounting the stage hides nothing
       they need (a world under /tmp included). */
    const uint64_t RO = MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV;
    const uint64_t RW = MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV;
    static const char *const RW_SUB[] = {"hold", "proposed", "tests/proposed"};
    /* /etc/alternatives: on Debian-family images /usr/bin/python3 is a link through it. the rest
       of /etc stays out (a root tool could read /etc/shadow). */
    static const char *const SYS[] = {"/usr", "/lib", "/lib64", "/lib32", "/libx32", "/bin", "/sbin",
                                      "/etc/alternatives"};
    enum { NRW = sizeof RW_SUB / sizeof *RW_SUB, NSYS = sizeof SYS / sizeof *SYS };
    int world = clone_tree(".", RO), rw[NRW], sys[NSYS], nul = -1, rc = -1;
    char link_to[NSYS][PATH_MAX];
    for (int i = 0; i < NRW; i++) rw[i] = -1;
    for (int i = 0; i < NSYS; i++) { sys[i] = -1; link_to[i][0] = 0; }
    if (world < 0) goto out;
    for (int i = 0; i < NRW; i++) {
        struct stat st;
        if (lstat(RW_SUB[i], &st) != 0) { if (errno == ENOENT) continue; goto out; }
        if (!S_ISDIR(st.st_mode)) goto out;          /* hold -> elsewhere would be a way out */
        if ((rw[i] = clone_tree(RW_SUB[i], RW)) < 0) goto out;
    }
    for (int i = 0; i < NSYS; i++) {
        struct stat st;
        if (lstat(SYS[i], &st) != 0) continue;
        if (S_ISLNK(st.st_mode)) {
            ssize_t l = readlink(SYS[i], link_to[i], sizeof link_to[i] - 1);
            if (l <= 0) goto out;
            link_to[i][l] = 0;
        } else if (S_ISDIR(st.st_mode) && (sys[i] = clone_tree(SYS[i], RO)) < 0) goto out;
    }
    if ((nul = clone_tree("/dev/null", MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID)) < 0) goto out;

    /* the new root: a small tmpfs, built, then pivoted into and made read-only. */
    if (syscall(__NR_mount, "bench", NS_STAGE, "tmpfs", MS_NOSUID | MS_NODEV, "size=1m,mode=0755") != 0) goto out;
    /* the private /tmp goes in before the world, so a world that lives under /tmp is mounted
       on top of it, not hidden by it. */
    if (mkdir(NS_STAGE "/tmp", 0755) != 0 ||
        syscall(__NR_mount, "bench-tmp", NS_STAGE "/tmp", "tmpfs", MS_NOSUID | MS_NODEV, "size=64m,mode=1777") != 0)
        goto out;
    if (snprintf(at, sizeof at, NS_STAGE "%s", w) >= (int)sizeof at || mkdir_p(at) || sc_move(world, at)) goto out;
    for (int i = 0; i < NRW; i++) {
        if (rw[i] < 0) continue;
        if (snprintf(at, sizeof at, NS_STAGE "%s/%s", w, RW_SUB[i]) >= (int)sizeof at || sc_move(rw[i], at)) goto out;
    }
    for (int i = 0; i < NSYS; i++) {
        if (snprintf(at, sizeof at, NS_STAGE "%s", SYS[i]) >= (int)sizeof at) goto out;
        if (link_to[i][0] && symlink(link_to[i], at) != 0) goto out;
        if (sys[i] >= 0 && (mkdir_p(at) || sc_move(sys[i], at))) goto out;
    }
    if (mkdir(NS_STAGE "/dev", 0755) != 0) goto out;
    int f = open(NS_STAGE "/dev/null", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0666);
    if (f < 0) goto out;
    close(f);
    if (sc_move(nul, NS_STAGE "/dev/null")) goto out;
    if (mkdir(NS_STAGE "/.old", 0700) != 0 || syscall(__NR_pivot_root, NS_STAGE, NS_STAGE "/.old") != 0) goto out;
    if (chdir("/") != 0 || syscall(__NR_umount2, "/.old", MNT_DETACH) != 0 || rmdir("/.old") != 0) goto out;
    if (sc_setattr(AT_FDCWD, "/", 0, MOUNT_ATTR_RDONLY) != 0) goto out;
    if (chdir(w) != 0) goto out;
    rc = 0;
out:
    if (world >= 0) close(world);
    if (nul >= 0) close(nul);
    for (int i = 0; i < NRW; i++) if (rw[i] >= 0) close(rw[i]);
    for (int i = 0; i < NSYS; i++) if (sys[i] >= 0) close(sys[i]);
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
    /* namespaces first (they need mount and unshare), then landlock (needs open() on the
       tree it now sees), then seccomp, which takes those syscalls away for good. */
    if (sandbox_world_only() != 0) return -1;
    if (jail == JAIL_FULL && landlock_write_jail() != 0) return -1;
    if (seccomp_deny_ambient() != 0) return -1;
    return 0;
}
