/* main.c — bench: run | kill | demo | snap-ls | status | restore | verify | fork | rules
 *
 * the fixture intern is a text file of opcodes. one op per frame.
 * illegal lines die at birth, before a single frame runs.
 * status reads the lamp byte from disk. there is no second copy to disagree with.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <dirent.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "arm.h"
#include "frame.h"
#include "mailbox.h"
#include "refusal.h"
#include "sha256.h"

/* the crown, baked at build. make generates rom_hash.h from the live tests/rom;
   a bare `cc` build without it runs UNPINNED (warns, does not enforce). */
#if defined(__has_include)
#  if __has_include("rom_hash.h")
#    include "rom_hash.h"
#  endif
#endif
#ifndef ROM_HASH
#  define ROM_HASH "UNPINNED"
#endif

#define N_CEIL     8     /* foundation is Touch/Chunk. past this is SET_LOOP, Ring 0, not here. */
#define MAX_OPS    64
#define MAX_ARGV   16
#define LINE_BYTES 512

typedef struct {
    Op       op;
    int      line;
    char     slot[128];   /* READ/WRITE: slot name. EXEC: program. TEST: kind. */
    char     path[256];
    char     rest[256];   /* WRITE payload, EXEC args */
    uint32_t ms;
} Instr;

static int g_log = -1;
static const char *g_root = ".";

static const char *OP_NAME[] = {"", "READ", "WRITE", "EXEC", "TEST", "WAIT"};
static const char *SLOT_NAME[SLOT_N] = {"fs", "tty", "fb", "judge", "radio"};
static const char *SUPER_NAME[] = {"INSTALL_ROM", "SET_LOOP", "KILL", "UNPLUG"};
static const char *KIND_NAME[] = {"PURE", "SCALAR", "JUDGE", "VISUAL"};

static void on_signal(int sig) { (void)sig; g_halt = 1; }

static int ev(Session *s, int rc, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(s->ev, sizeof s->ev, fmt, ap);
    va_end(ap);
    return rc;
}

static int slot_of(const char *name) {
    for (int i = 0; i < SLOT_N; i++) if (!strcmp(name, SLOT_NAME[i])) return i;
    return -1;
}

static int prefix(const char *s, const char *p) { return strncmp(s, p, strlen(p)) == 0; }

static int suffix(const char *s, const char *x) {
    size_t a = strlen(s), b = strlen(x);
    return a >= b && !strcmp(s + a - b, x);
}

/* relative, inside the world, no climbing. */
static int safe_rel(const char *p) { return p[0] && p[0] != '/' && !strstr(p, ".."); }

static char *tok(char **p) {
    while (**p == ' ' || **p == '\t') (*p)++;
    if (!**p) return NULL;
    char *start = *p;
    while (**p && **p != ' ' && **p != '\t') (*p)++;
    if (**p) *(*p)++ = 0;
    return start;
}

static char *trim(char *p) {
    while (*p == ' ' || *p == '\t') p++;
    size_t n = strlen(p);
    while (n && (p[n-1] == ' ' || p[n-1] == '\t')) p[--n] = 0;
    return p;
}

static int copy_field(char *dst, size_t n, const char *src) {
    size_t l = strlen(src);
    if (l >= n) return -1;
    memcpy(dst, src, l + 1);
    return 0;
}

/* every parse refusal names its rule (refusal.c); the caller prints the fix under it. */
#define FAULT(r, ...) do { snprintf(err, errsz, __VA_ARGS__); *rule = (r); return -1; } while (0)

/* 1 = instruction, 0 = blank/comment, -1 = fault */
static int parse_line(char *ln, int lineno, Instr *in, char *err, size_t errsz, const char **rule) {
    ln[strcspn(ln, "\r\n")] = 0;
    char *p = ln;
    while (*p == ' ' || *p == '\t') p++;
    if (!*p || *p == '#') return 0;   /* chat is a comment track */

    memset(in, 0, sizeof *in);
    in->line = lineno;
    char *verb = tok(&p);
    for (size_t i = 0; i < sizeof SUPER_NAME / sizeof *SUPER_NAME; i++)
        if (!strcasecmp(verb, SUPER_NAME[i])) FAULT("verb-super", "%s is supervisor; intern emitting it is a spec bug", SUPER_NAME[i]);

    int op = 0;
    for (int i = OP_READ; i <= OP_WAIT; i++) if (!strcasecmp(verb, OP_NAME[i])) op = i;
    if (!op) FAULT("verb-unknown", "unknown verb '%.64s' (five: READ WRITE EXEC TEST WAIT)", verb);
    in->op = (Op)op;

    char *a = tok(&p), *b;
    switch (in->op) {
    case OP_READ:
    case OP_WRITE:
        b = tok(&p);
        if (!a || !b) FAULT("shape-rw", "%s needs <slot> <path>", OP_NAME[op]);
        if (copy_field(in->slot, sizeof in->slot, a) || copy_field(in->path, sizeof in->path, b)) FAULT("field-long", "field too long");
        if (!safe_rel(in->path)) FAULT("path-escape", "path escapes the world: %.160s", in->path);
        if (in->op == OP_READ && *trim(p)) FAULT("read-payload", "READ takes no payload");
        if (in->op == OP_WRITE) {
            /* ring 1/2: intern writes quarantine and drafts. main/ and tests/rom/ are ring 0. */
            if (!prefix(in->path, "hold/") && !prefix(in->path, "proposed/"))
                FAULT("write-ring", "ring: intern writes hold/ or proposed/ only, not %.160s", in->path);
            if (copy_field(in->rest, sizeof in->rest, trim(p))) FAULT("field-long", "payload too long");
        }
        return 1;
    case OP_EXEC:
        if (!a) FAULT("exec-shape", "EXEC needs <program>");
        if (copy_field(in->slot, sizeof in->slot, a)) FAULT("field-long", "field too long");
        if (!safe_rel(a) || !prefix(a, "tools/") || !suffix(a, ".py")) FAULT("exec-prog", "EXEC runs tools/*.py only, not %.160s", a);
        if (copy_field(in->rest, sizeof in->rest, trim(p))) FAULT("field-long", "args too long");
        {
            char tmp[256], *q = tmp, *t;
            memcpy(tmp, in->rest, sizeof tmp);
            while ((t = tok(&q)) != NULL) if (!safe_rel(t)) FAULT("exec-arg", "arg escapes the world: %.160s", t);
        }
        return 1;
    case OP_TEST:
        b = tok(&p);
        {
            int k = -1;
            for (int i = 0; a && i < 4; i++) if (!strcasecmp(a, KIND_NAME[i])) k = i;
            if (k < 0) FAULT("test-kind", "TEST without kind (PURE SCALAR JUDGE VISUAL)");
            if (!b) FAULT("test-shape", "TEST needs <kind> <path>");
            snprintf(in->slot, sizeof in->slot, "%s", KIND_NAME[k]);
        }
        if (copy_field(in->path, sizeof in->path, b)) FAULT("field-long", "field too long");
        if (!safe_rel(b) || !prefix(b, "tests/rom/") || !suffix(b, ".py")) FAULT("test-path", "TEST runs tests/rom/*.py only, not %.160s", b);
        if (*trim(p)) FAULT("test-shape", "TEST takes <kind> <path> only");
        return 1;
    case OP_WAIT: {
        if (!a) FAULT("wait-shape", "WAIT needs <ms>");
        char *end;
        errno = 0;
        unsigned long ms = strtoul(a, &end, 10);
        if (errno || *end || a[0] == '-' || ms > 3600000ul) FAULT("wait-shape", "WAIT <ms> not a number: %.160s", a);
        if (*trim(p)) FAULT("wait-shape", "WAIT takes <ms> only");
        in->ms = (uint32_t)ms;
        return 1;
    }
    }
    FAULT("internal", "unreachable");
}

/* ---- the five actuators, as tools behind the frame ---- */

static int wired(Session *s, int slot, const char *name) {
    if (slot < 0) return ev(s, 1, "deny slot=%s unknown rule=slot-unknown", name);
    if (!plugged(&s->bus, slot)) return ev(s, 1, "deny slot=%s unplugged rule=slot-pulled", name);
    return 0;
}

/* ---- tool output: one file per step, never the log ----
 * sessions/<id>/log is the supervisor's and the mailbox's. what a tool prints, and the bytes
 * a READ returns, go to sessions/<id>/out-<n>; the MANIFEST pins that file by size and sha256.
 * a tool cannot write a line into the log, so it cannot write a line that looks like the helper. */

static int out_open(Session *s, char *name, size_t n) {
    char p[1100];
    snprintf(name, n, "out-%u", s->n + 1);
    if (path_join(p, sizeof p, s->dir, name)) return -1;
    return open(p, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
}

/* close the step's out file and pin it in s->out. */
static void out_close(Session *s, int fd, const char *name) {
    char p[1100], hex[65] = "unreadable";
    if (fd >= 0) close(fd);
    uint64_t bytes = 0;
    if (!path_join(p, sizeof p, s->dir, name)) {
        int in = open(p, O_RDONLY | O_CLOEXEC);
        if (in >= 0) {
            Sha256 c;
            sha256_init(&c);
            char buf[8192];
            ssize_t r;
            while ((r = read(in, buf, sizeof buf)) > 0) { sha256_update(&c, buf, (size_t)r); bytes += (uint64_t)r; }
            close(in);
            if (r == 0) sha256_final(&c, hex);
        }
    }
    snprintf(s->out, sizeof s->out, "%s bytes=%llu sha256=%s", name, (unsigned long long)bytes, hex);
}

/* ---- symlink-safe file access anchored at the world root ----
 * the supervisor runs as the owner and its READ/WRITE only string-checked the path prefix, so an
 * intern that planted a symlink in hold/ (via an EXEC tool) could make a later WRITE follow it out
 * of the world and write anywhere the owner can. these walk every component with O_NOFOLLOW from a
 * dirfd opened at the world root: no symlink is ever traversed, so hold/evil -> /etc is inert. */
static void split_dir(const char *rel, char *dir, size_t dn, const char **base) {
    const char *slash = strrchr(rel, '/');
    if (!slash) { dir[0] = 0; *base = rel; return; }
    size_t l = (size_t)(slash - rel);
    if (l >= dn) l = dn - 1;
    memcpy(dir, rel, l);
    dir[l] = 0;
    *base = slash + 1;
}

/* open <reldir> under rootfd one component at a time, refusing any symlink. make=1 creates missing
   components. reldir must be relative and free of ".." (safe_rel upstream). fd on success, else -1. */
static int open_dir_beneath(int rootfd, const char *reldir, int make) {
    int cur = openat(rootfd, ".", O_DIRECTORY | O_RDONLY | O_CLOEXEC);
    if (cur < 0) return -1;
    const char *p = reldir;
    while (*p) {
        while (*p == '/') p++;
        if (!*p) break;
        char comp[256];
        size_t len = 0;
        while (p[len] && p[len] != '/') len++;
        if (len >= sizeof comp) { close(cur); errno = ENAMETOOLONG; return -1; }
        memcpy(comp, p, len);
        comp[len] = 0;
        p += len;
        if (make) mkdirat(cur, comp, 0755);   /* EEXIST is fine; a symlink here is caught next */
        int nx = openat(cur, comp, O_DIRECTORY | O_NOFOLLOW | O_RDONLY | O_CLOEXEC);
        close(cur);
        if (nx < 0) return -1;                 /* ELOOP if comp is a symlink: the escape is refused */
        cur = nx;
    }
    return cur;
}

static int t_read(Session *s, void *arg) {
    Instr *in = arg;
    int sl = slot_of(in->slot);
    if (wired(s, sl, in->slot)) return 1;
    if (sl != SLOT_FS) return ev(s, 1, "deny slot=%s no device in foundation rule=slot-pulled", in->slot);
    char buf[4097], dir[1024];
    const char *base;
    int rootfd = open(s->root, O_DIRECTORY | O_RDONLY | O_CLOEXEC);
    if (rootfd < 0) return ev(s, 1, "op=read path=%s err=no world root rule=internal", in->path);
    split_dir(in->path, dir, sizeof dir, &base);
    int dfd = open_dir_beneath(rootfd, dir, 0);
    close(rootfd);
    if (dfd < 0) return ev(s, 1, "op=read slot=fs path=%s err=%s rule=fs-path", in->path, strerror(errno));
    /* O_NONBLOCK so a fifo/device planted in hold/ cannot block the frame clock; then require a
       regular file — a fifo, socket or device is not board state and is refused, not read. */
    int rf = openat(dfd, base, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    close(dfd);
    if (rf < 0) return ev(s, 1, "op=read slot=fs path=%s err=%s rule=fs-path", in->path, strerror(errno));
    struct stat rst;
    if (fstat(rf, &rst) != 0 || !S_ISREG(rst.st_mode)) {
        close(rf);
        return ev(s, 1, "op=read slot=fs path=%s err=not a regular file rule=fs-path", in->path);
    }
    size_t cap = s->bus.cap[SLOT_FS], n = 0;   /* buf is cap+1 wide: reading it full means over cap */
    ssize_t r;
    while (n < sizeof buf && (r = read(rf, buf + n, sizeof buf - n)) > 0) n += (size_t)r;
    close(rf);
    if (n > cap) return ev(s, 1, "leash op=read path=%s bytes>%zu rule=fs-cap", in->path, cap);
    char name[32];
    int fd = out_open(s, name, sizeof name);
    if (fd < 0) return ev(s, 1, "op=read path=%s err=cannot open out file rule=internal", in->path);
    int bad = n && write(fd, buf, n) != (ssize_t)n;
    out_close(s, fd, name);
    if (bad) return ev(s, 1, "op=read path=%s err=short write to %s rule=internal", in->path, name);
    dprintf(g_log, "READ fs %s %zu bytes -> %s\n", in->path, n, name);
    return ev(s, 0, "op=read kind=none slot=fs path=%s bytes=%zu dirty=0", in->path, n);
}

/* write text to <base> in dfd atomically (temp + renameat), refusing to follow a symlink at base. */
static int write_beneath(int dfd, const char *base, const char *text, size_t n) {
    char tmp[300];
    if (snprintf(tmp, sizeof tmp, "%s.benchtmp", base) >= (int)sizeof tmp) return -1;
    unlinkat(dfd, tmp, 0);                 /* clear a leftover temp (e.g. a crash, or a planted fifo) */
    int fd = openat(dfd, tmp, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0644);
    if (fd < 0) return -1;                 /* O_EXCL: the temp is a fresh regular file, never a device */
    int bad = n && write(fd, text, n) != (ssize_t)n;
    if (close(fd) != 0) bad = 1;
    if (bad) { unlinkat(dfd, tmp, 0); return -1; }
    if (renameat(dfd, tmp, dfd, base) != 0) { unlinkat(dfd, tmp, 0); return -1; }
    return 0;
}

static int t_write(Session *s, void *arg) {
    Instr *in = arg;
    int sl = slot_of(in->slot);
    if (wired(s, sl, in->slot)) return 1;
    if (sl != SLOT_FS) return ev(s, 1, "deny slot=%s no device in foundation rule=slot-pulled", in->slot);
    char text[300], dir[1024];
    const char *base;
    snprintf(text, sizeof text, "%s%s", in->rest, in->rest[0] ? "\n" : "");
    size_t n = strlen(text);
    if (n > s->bus.cap[SLOT_FS]) return ev(s, 1, "leash op=write bytes>%u rule=fs-cap", s->bus.cap[SLOT_FS]);
    int rootfd = open(s->root, O_DIRECTORY | O_RDONLY | O_CLOEXEC);
    if (rootfd < 0) return ev(s, 1, "op=write path=%s err=no world root rule=internal", in->path);
    split_dir(in->path, dir, sizeof dir, &base);
    int dfd = open_dir_beneath(rootfd, dir, 1);
    close(rootfd);
    if (dfd < 0) return ev(s, 1, "op=write path=%s err=%s rule=fs-path", in->path, strerror(errno));
    int bad = write_beneath(dfd, base, text, n);
    close(dfd);
    if (bad) return ev(s, 1, "op=write path=%s err=%s rule=fs-path", in->path, strerror(errno));
    dprintf(g_log, "WRITE fs %s %zu bytes\n", in->path, n);
    return ev(s, 0, "op=write kind=none slot=fs path=%s bytes=%zu dirty=0", in->path, n);
}

static int t_exec(Session *s, void *arg) {
    Instr *in = arg;
    if (wired(s, SLOT_FS, "fs")) return 1;   /* tools live on fs */
    char args[256], *q = args, *t, *argv[MAX_ARGV + 3];
    int c = 0;
    memcpy(args, in->rest, sizeof args);
    argv[c++] = "python3";
    argv[c++] = in->slot;
    while ((t = tok(&q)) != NULL) {
        if (c >= MAX_ARGV + 2) return ev(s, 1, "op=exec too many args rule=exec-argc");
        argv[c++] = t;
    }
    argv[c] = NULL;
    uint64_t nb = 0;
    char name[32];
    int fd = out_open(s, name, sizeof name);
    if (fd < 0) return ev(s, 1, "op=exec prog=%s err=cannot open out file rule=internal", in->slot);
    dprintf(g_log, "EXEC %s %s -> %s\n", in->slot, in->rest, name);
    int rc = child_run(s->root, argv, JAIL_FULL, NULL, 0, &nb, s->t_tool_ms, OUT_CEIL_BYTES, fd, fd);
    out_close(s, fd, name);
    if (rc == -2) return ev(s, 1, "knife op=exec prog=%s timeout>%ums rule=t-tool", in->slot, s->t_tool_ms);
    if (rc == -3) return ev(s, 1, "halt op=exec prog=%s child killed rule=kill", in->slot);
    if (rc == -4) return ev(s, 1, "leash op=exec prog=%s out>%u killed rule=out-ceil", in->slot, OUT_CEIL_BYTES);
    if (rc == -5) return ev(s, 1, "deny op=exec prog=%s sandbox SIGSYS rule=sandbox", in->slot);
    if (rc == -6) return ev(s, 1, "deny op=exec prog=%s worker not started rule=worker-setup", in->slot);
    if (nb > s->bus.cap[SLOT_TTY]) return ev(s, 1, "leash op=exec out=%llu>%u rule=tty-cap", (unsigned long long)nb, s->bus.cap[SLOT_TTY]);
    return ev(s, rc != 0, "op=exec kind=none slot=%s rc=%d out=%llu dirty=0", in->slot, rc, (unsigned long long)nb);
}

static int t_test(Session *s, void *arg) {
    Instr *in = arg;
    if (!strcmp(in->slot, "JUDGE")) {
        /* dirty DMA needs the judge card and the radio. radio is off. */
        if (!plugged(&s->bus, SLOT_JUDGE) || !plugged(&s->bus, SLOT_RADIO))
            return ev(s, 1, "deny op=test kind=judge judge/radio unplugged rule=judge-pulled");
        return ev(s, 1, "deny op=test kind=judge no judge device in foundation rule=judge-pulled");
    }
    if (!strcmp(in->slot, "VISUAL")) {
        if (!plugged(&s->bus, SLOT_FB)) return ev(s, 1, "deny op=test kind=visual fb unplugged rule=visual-pulled");
        return ev(s, 1, "deny op=test kind=visual no fb device in foundation rule=visual-pulled");
    }
    char *argv[] = {"python3", "tools/test_runner.py", "--kind", in->slot, in->path, NULL};
    char out[256] = "", name[32];
    int fd = out_open(s, name, sizeof name);
    if (fd < 0) return ev(s, 1, "op=test path=%s err=cannot open out file rule=internal", in->path);
    dprintf(g_log, "TEST %s %s -> %s\n", in->slot, in->path, name);
    int rc = child_run(s->root, argv, JAIL_NET_ONLY, out, sizeof out, NULL, s->t_tool_ms, OUT_CEIL_BYTES, fd, fd);
    out_close(s, fd, name);
    out[strcspn(out, "\r\n")] = 0;
    if (rc == -2) return ev(s, 1, "knife op=test path=%s timeout>%ums rule=t-tool", in->path, s->t_tool_ms);
    if (rc == -3) return ev(s, 1, "halt op=test path=%s child killed rule=kill", in->path);
    if (rc == -4) return ev(s, 1, "leash op=test path=%s out>%u killed rule=out-ceil", in->path, OUT_CEIL_BYTES);
    if (rc == -5) return ev(s, 1, "deny op=test path=%s sandbox SIGSYS rule=sandbox", in->path);
    if (rc == -6) return ev(s, 1, "deny op=test path=%s worker not started rule=worker-setup", in->path);
    return ev(s, rc != 0, "op=test kind=%s slot=fs path=%s rc=%d result=\"%s\" dirty=0",
              !strcmp(in->slot, "PURE") ? "pure" : "scalar", in->path, rc, out);
}

static int t_wait(Session *s, void *arg) {
    Instr *in = arg;
    if (in->ms > s->t_tool_ms) return ev(s, 1, "op=wait ms=%u > T_tool=%u rule=t-tool", in->ms, s->t_tool_ms);
    struct timespec ts = {(time_t)(in->ms / 1000), (long)(in->ms % 1000) * 1000000L}, rem;
    uint64_t t0 = nowns();
    /* a stray signal resumes the sleep; a halt ends it. evidence says what was slept. */
    while (nanosleep(&ts, &rem) != 0 && errno == EINTR && !g_halt) ts = rem;
    unsigned long long slept = (nowns() - t0) / 1000000ull;
    return ev(s, 0, "op=wait kind=none ms=%u slept=%llu%s dirty=0", in->ms, slept, g_halt ? " halted" : "");
}

static const Tool TOOL[] = {NULL, t_read, t_write, t_exec, t_test, t_wait};

/* ---- session files ---- */

static int sessions_path(char *out, size_t n, const char *name) {
    char base[1024];
    if (path_join(base, sizeof base, g_root, "sessions")) return -1;
    return name ? path_join(out, n, base, name) : (snprintf(out, n, "%s", base) >= (int)n ? -1 : 0);
}

static int read_small(const char *path, char *buf, size_t n) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    size_t r = fread(buf, 1, n - 1, f);
    fclose(f);
    buf[r] = 0;
    return 0;
}

static int current_dir(char *dir, size_t n, char *id, size_t idn) {
    char cur[1024];
    if (sessions_path(cur, sizeof cur, "CURRENT") || read_small(cur, id, idn)) return -1;
    id[strcspn(id, "\r\n")] = 0;
    return id[0] ? sessions_path(dir, n, id) : -1;
}

static const char *kv(const char *text, const char *key, char *out, size_t n) {
    size_t kl = strlen(key);
    for (const char *p = text; p && *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : NULL) {
        if (!strncmp(p, key, kl) && p[kl] == '=') {
            size_t l = strcspn(p + kl + 1, "\n");
            if (l >= n) l = n - 1;
            memcpy(out, p + kl + 1, l);
            out[l] = 0;
            return out;
        }
    }
    out[0] = 0;
    return NULL;
}

static int exists(const char *dir, const char *name) {
    char p[1100];
    struct stat st;
    return !path_join(p, sizeof p, dir, name) && stat(p, &st) == 0;
}

/* ---- ROM crown: refuse to boot on a changed image ---- */

static int rom_ok(void) {
    if (!strcmp(ROM_HASH, "UNPINNED")) {
        fprintf(stderr, "warn: ROM not pinned (built without rom_hash.h); run `make` to crown it\n");
        return 0;
    }
    const char *paths[] = {"tests/rom"};
    char hex[65];
    if (tree_hash(g_root, paths, 1, hex) != 0) {
        fprintf(stderr, "boot: cannot hash tests/rom under %s\n", g_root);
        return -1;
    }
    if (strcmp(hex, ROM_HASH) != 0) {
        fprintf(stderr,
                "boot: ROM image changed — refusing to run.\n"
                "  embedded %s\n  on disk  %s\n"
                "changing tests/rom is Ring 0: rebuild with `make` (a human key), not a live edit.\n",
                ROM_HASH, hex);
        return -1;
    }
    return 0;
}

/* ---- session arm: the owner's token, v0 ----
 *
 * run refuses to start unless the owner armed it: BENCH_TOKEN names an existing regular
 * file, or sessions/OWNER_TOKEN exists under the world root. presence only, no content.
 * the token is checked here, in the supervisor, before any session dir, frame or lamp.
 * the intern cannot mint it: WRITE takes hold/ and proposed/ only, and EXEC children are
 * write-limited to hold/ and proposed/. TEST children are not write-limited; they run ROM
 * code, which a human crowned. stands in for a later hardware key; nothing more.
 * the helper (bench-helper, over the mailbox) must agree at start (ARM_OK) and before
 * every frame (FRAME_OK). it can refuse; it cannot arm on its own. missing or silent
 * helper = fail closed, exit 6. */

static int arm_read(TokenId *t, char *why, size_t n) {
    return token_read(g_root, getenv("BENCH_TOKEN"), t, why, n);
}

static Mailbox g_mb = {-1, -1, -1};

/* ---- world lock: one run per world ----
 * a POSIX write lock (fcntl) on sessions/LOCK, held for the life of `run`. fcntl rather than
 * flock because F_GETLK names the holder's pid: `kill` signals a pid only when the lock proves
 * that pid is the live run. the lock dies with the process, so a crashed run holds nothing.
 * note: POSIX locks drop when the holder closes ANY fd on the file — run opens LOCK once. */

/* take the lock on sessions/<name>. 0 held; -1 busy (holder in *pid, if known); -2 cannot open. */
static int lock_take_at(const char *name, int *fd_out, pid_t *pid) {
    char p[1100];
    *pid = 0;
    if (sessions_path(p, sizeof p, name)) return -2;
    int fd = open(p, O_RDWR | O_CREAT | O_CLOEXEC, 0644);
    if (fd < 0) return -2;
    struct flock fl = {.l_type = F_WRLCK, .l_whence = SEEK_SET, .l_start = 0, .l_len = 0};
    if (fcntl(fd, F_SETLK, &fl) != 0) {
        struct flock q = {.l_type = F_WRLCK, .l_whence = SEEK_SET, .l_start = 0, .l_len = 0};
        if (fcntl(fd, F_GETLK, &q) == 0 && q.l_type != F_UNLCK) *pid = q.l_pid;
        close(fd);
        return -1;
    }
    *fd_out = fd;   /* held until exit; never closed early */
    return 0;
}

static int lock_take(int *fd_out, pid_t *pid) { return lock_take_at("LOCK", fd_out, pid); }

/* the pid of the live process holding sessions/<name>, or 0 if nobody does. */
static pid_t lock_holder_at(const char *name) {
    char p[1100];
    if (sessions_path(p, sizeof p, name)) return 0;
    int fd = open(p, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    struct flock q = {.l_type = F_WRLCK, .l_whence = SEEK_SET, .l_start = 0, .l_len = 0};
    pid_t pid = (fcntl(fd, F_GETLK, &q) == 0 && q.l_type != F_UNLCK) ? q.l_pid : 0;
    close(fd);
    return pid;
}

static pid_t lock_holder(void) { return lock_holder_at("LOCK"); }

/* ---- commands ---- */

static int cmd_status(void) {
    char dir[1024], id[128], path[1100], st[1024], v[64];
    if (current_dir(dir, sizeof dir, id, sizeof id)) {
        printf("lamps   0x00 (dark)\nsession none\n");
        return 0;
    }
    if (path_join(path, sizeof path, dir, "STATE") || read_small(path, st, sizeof st)) {
        fprintf(stderr, "status: session %s has no STATE\n", id);
        return 1;
    }
    unsigned lamps = (unsigned)strtoul(kv(st, "lamps", v, sizeof v) ? v : "0", NULL, 16);
    unsigned plug = (unsigned)strtoul(kv(st, "plug", v, sizeof v) ? v : "0", NULL, 16);
    if ((lamps & LAMP_MAIN) && (lamps & LAMP_HOLD)) {
        fprintf(stderr, "status: lamp byte 0x%02x has MAIN and HOLD lit — fault\n", lamps);
        return 1;
    }
    char status[32], sn[32], n[16], N[16], K[16];
    kv(st, "status", status, sizeof status);
    /* STATE says running, but nobody holds the world: the run died without writing an end. */
    if (!strcmp(status, "run") && lock_holder() == 0) snprintf(status, sizeof status, "crashed");
    printf("session %s %s%s\n", id, status, exists(dir, "KILL") ? " (killed)" : "");
    printf("lamps   0x%02x", lamps);
    if (lamps & LAMP_MAIN) printf(" MAIN");
    if (lamps & LAMP_HOLD) printf(" HOLD");
    if (lamps & LAMP_BLIND) printf(" BLIND");
    printf("\nsnap    %s\n", kv(st, "snap", sn, sizeof sn) ? sn : "-");
    printf("n/N     %s/%s K=%s\n", kv(st, "n", n, sizeof n) ? n : "?",
           kv(st, "N", N, sizeof N) ? N : "?", kv(st, "K", K, sizeof K) ? K : "?");
    printf("slots   0x%02x", plug);
    for (int i = 0; i < SLOT_N; i++) if ((plug >> i) & 1) printf(" %s", SLOT_NAME[i]);
    printf(" | pulled");
    for (int i = 0; i < SLOT_N; i++) if (!((plug >> i) & 1)) printf(" %s", SLOT_NAME[i]);
    printf("\n");
    return 0;
}

/* one line, the owner's whole board, grep-able. STATE + SESSION, plus three live readings:
   hold growth now, armed now, and who holds the world. no JSON, no dashboard. */
static int cmd_status_line(void) {
    char dir[1024], id[128], path[1100], st[1024], se[1024], v[64];
    TokenId t;
    char tw[256];
    const char *armed_now = arm_read(&t, tw, sizeof tw) ? "yes" : "no";
    pid_t holder = lock_holder();
    if (current_dir(dir, sizeof dir, id, sizeof id)) {
        printf("none dark armed=%s lock=%s\n", armed_now, holder ? "held" : "free");
        return 0;
    }
    if (path_join(path, sizeof path, dir, "STATE") || read_small(path, st, sizeof st)) {
        printf("%s nostate armed=%s lock=%s\n", id, armed_now, holder ? "held" : "free");
        return 1;
    }
    se[0] = 0;
    if (!path_join(path, sizeof path, dir, "SESSION")) read_small(path, se, sizeof se);

    char status[32], sn[32], n[16], N[16], helper[32];
    kv(st, "status", status, sizeof status);
    if (!strcmp(status, "run") && !holder) snprintf(status, sizeof status, "crashed");
    unsigned lamps = (unsigned)strtoul(kv(st, "lamps", v, sizeof v) ? v : "0", NULL, 16);
    char lit[32] = "";
    if (lamps & LAMP_MAIN) strcat(lit, "MAIN,");
    if (lamps & LAMP_HOLD) strcat(lit, "HOLD,");
    if (lamps & LAMP_BLIND) strcat(lit, "BLIND,");
    if (lit[0]) lit[strlen(lit) - 1] = 0; else snprintf(lit, sizeof lit, "dark");

    unsigned long long qb = strtoull(kv(se, "hold_quota", v, sizeof v) ? v : "0", NULL, 10);
    unsigned long long bb = strtoull(kv(se, "hold_base", v, sizeof v) ? v : "0", NULL, 10);
    unsigned long long qf = strtoull(kv(se, "hold_files_quota", v, sizeof v) ? v : "0", NULL, 10);
    unsigned long long bf = strtoull(kv(se, "hold_base_files", v, sizeof v) ? v : "0", NULL, 10);
    uint64_t hb = 0, hf = 0;
    char hp[1100];
    if (!path_join(hp, sizeof hp, g_root, "hold")) tree_count(hp, &hb, &hf);
    long long db = (long long)hb - (long long)bb, df = (long long)hf - (long long)bf;

    printf("%s %s%s n=%s/%s snap=%s lamps=%s hold=%+lld/%llu files=%+lld/%llu armed=%s helper=%s lock=%s\n",
           id, status, exists(dir, "KILL") ? ",killed" : "",
           kv(st, "n", n, sizeof n) ? n : "?", kv(st, "N", N, sizeof N) ? N : "?",
           kv(st, "snap", sn, sizeof sn) ? sn : "-", lit, db, qb, df, qf, armed_now,
           kv(se, "helper", helper, sizeof helper) ? helper : "-", holder ? "held" : "free");
    return 0;
}

static void fmt_instr(const Instr *in, char *out, size_t n) {
    switch (in->op) {
    case OP_WAIT: snprintf(out, n, "WAIT %u\n", in->ms); break;
    case OP_EXEC: snprintf(out, n, "EXEC %s%s%s\n", in->slot, in->rest[0] ? " " : "", in->rest); break;
    default:
        snprintf(out, n, "%s %s %s%s%s\n", OP_NAME[in->op], in->slot, in->path,
                 in->rest[0] ? " " : "", in->rest);
    }
}

/* the frame's gate. KILL first (the owner's hand), then the owner's token — the same file,
   untouched since arm — then the helper. */
static int run_gate(Session *s) {
    if (g_halt || exists(s->dir, "KILL")) return ev(s, 3, "halt=kill rule=kill");
    TokenId now;
    char tw[256];
    if (!arm_read(&now, tw, sizeof tw)) return ev(s, 5, "halt=disarmed %.200s rule=disarmed", tw);
    if (!token_same(&now, &s->tok)) return ev(s, 5, "halt=disarmed owner token changed since arm rule=disarmed");
    char n[16], why[128];
    snprintf(n, sizeof n, "%u", s->n + 1);
    int ok = mb_ask(&g_mb, "FRAME_OK", n, why, sizeof why);
    if (ok < 0) return ev(s, 6, "halt=helper-lost no FRAME_OK answer rule=helper-lost");
    if (ok == 0) return ev(s, 5, "halt=disarmed helper: %.100s rule=disarmed", why);
    return 0;
}

/* ---- retention: sessions/ is a budget too ----
 * on run start, keep the newest KEEP session dirs, counting the one about to be made.
 * a session dir is sessions/<epoch>-<pid>; nothing else in sessions/ is touched. never pruned:
 * the CURRENT session, and any session holding hold.before (the owner's old hold/ from a
 * restore — bench does not delete the owner's data). removal uses lstat and never follows links. */
#define KEEP_DEFAULT 20u

static int rm_tree(const char *p) {
    struct stat st;
    if (lstat(p, &st) != 0) return errno == ENOENT ? 0 : -1;
    if (!S_ISDIR(st.st_mode)) return unlink(p);
    /* sealed snaps are 0555; our uid may restore write to remove them (unlink needs write on
       the parent dir). this is the only path that unseals, and it only does so to delete. */
    chmod(p, 0700);
    DIR *d = opendir(p);
    if (!d) return -1;
    int rc = 0;
    struct dirent *e;
    while (rc == 0 && (e = readdir(d)) != NULL) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char c[1100];
        rc = path_join(c, sizeof c, p, e->d_name) ? -1 : rm_tree(c);
    }
    closedir(d);
    return rc == 0 ? rmdir(p) : rc;
}

typedef struct { char name[64]; long long epoch; long long mt; } SessEnt;

static int sess_newest_first(const void *a, const void *b) {
    const SessEnt *x = a, *y = b;
    if (x->epoch != y->epoch) return x->epoch < y->epoch ? 1 : -1;
    if (x->mt != y->mt) return x->mt < y->mt ? 1 : -1;
    return strcmp(y->name, x->name);
}

static int is_session_name(const char *n, long long *epoch) {
    const char *dash = strchr(n, '-');
    if (!dash || dash == n || !dash[1] || strlen(n) >= 64) return 0;
    for (const char *c = n; *c; c++) if (c != dash && (*c < '0' || *c > '9')) return 0;
    *epoch = atoll(n);
    return 1;
}

/* returns how many session dirs were removed, -1 on error. */
static int retain(unsigned keep) {
    char sdir[1024], cur[128] = "", cdir[1024];
    if (sessions_path(sdir, sizeof sdir, NULL)) return -1;
    current_dir(cdir, sizeof cdir, cur, sizeof cur);
    DIR *d = opendir(sdir);
    if (!d) return -1;
    SessEnt *v = NULL;
    size_t n = 0, cap = 0;
    struct dirent *e;
    while ((e = readdir(d)) != NULL) {
        long long ep;
        char p[1100];
        struct stat st;
        if (!is_session_name(e->d_name, &ep) || path_join(p, sizeof p, sdir, e->d_name) ||
            lstat(p, &st) != 0 || !S_ISDIR(st.st_mode)) continue;
        if (n == cap) {
            cap = cap ? cap * 2 : 64;
            SessEnt *nv = realloc(v, cap * sizeof *nv);
            if (!nv) { free(v); closedir(d); return -1; }
            v = nv;
        }
        snprintf(v[n].name, sizeof v[n].name, "%s", e->d_name);
        v[n].epoch = ep;
        v[n].mt = (long long)st.st_mtim.tv_sec;
        n++;
    }
    closedir(d);
    qsort(v, n, sizeof *v, sess_newest_first);
    int removed = 0;
    for (size_t i = keep > 0 ? keep - 1 : 0; i < n; i++) {   /* keep-1 old + the new one = keep */
        char p[1100];
        if (!strcmp(v[i].name, cur) || path_join(p, sizeof p, sdir, v[i].name) || exists(p, "hold.before")) continue;
        if (rm_tree(p) == 0) removed++;
    }
    free(v);
    return removed;
}

/* plain decimal digits, nothing else: no sign, no suffix, no spaces. */
static int parse_bytes(const char *p, uint64_t *out) {
    if (!*p) return -1;
    uint64_t v = 0;
    for (; *p; p++) {
        if (*p < '0' || *p > '9') return -1;
        v = v * 10 + (uint64_t)(*p - '0');
        if (v > HOLD_QUOTA_CEIL) return -1;
    }
    *out = v;
    return 0;
}

static int cmd_run(int argc, char **argv) {
    if (rom_ok() != 0) return 4;
    TokenId tok;
    char tw[256];
    if (!arm_read(&tok, tw, sizeof tw)) {
        fprintf(stderr, "run: not armed — %s. set BENCH_TOKEN to a token file, or create %s "
                        "(yours, mode 0600 or 0644) under the world root. no frames ran.\n", tw, TOKEN_REL);
        return 5;
    }
    unsigned long n = N_MAX_DEFAULT;
    const char *script = NULL;
    /* hold quotas: the flag beats the env beats the built-in default. bytes and entries alike. */
    const char *hq_src = getenv("BENCH_HOLD_QUOTA"), *hf_src = getenv("BENCH_HOLD_FILES");
    const char *keep_src = getenv("BENCH_KEEP");
    if (hq_src && !*hq_src) hq_src = NULL;
    if (hf_src && !*hf_src) hf_src = NULL;
    if (keep_src && !*keep_src) keep_src = NULL;
    for (int i = 0; i < argc; i++) {
        if (!strcmp(argv[i], "--n") && i + 1 < argc) {
            char *end;
            n = strtoul(argv[++i], &end, 10);
            if (*end) n = 0;
        } else if (!strcmp(argv[i], "--hold-quota") && i + 1 < argc) {
            hq_src = argv[++i];
        } else if (!strcmp(argv[i], "--hold-files") && i + 1 < argc) {
            hf_src = argv[++i];
        } else if (!strcmp(argv[i], "--keep") && i + 1 < argc) {
            keep_src = argv[++i];
        } else if (!script) {
            script = argv[i];
        } else {
            fprintf(stderr, "usage: bench run [--n N] [--hold-quota BYTES] [--hold-files N] [--keep M] [script|-]\n");
            return 2;
        }
    }
    if (n == 0 || n > N_CEIL) {
        fprintf(stderr, "run: N=%lu out of range 1..%d (raising N is SET_LOOP, Ring 0)\n", n, N_CEIL);
        return 2;
    }
    uint64_t hold_quota = HOLD_QUOTA_BYTES;
    if (hq_src && parse_bytes(hq_src, &hold_quota) != 0) {
        fprintf(stderr, "run: hold quota '%.64s' is not a byte count 0..%llu\n",
                hq_src, (unsigned long long)HOLD_QUOTA_CEIL);
        return 2;
    }
    uint64_t keep = KEEP_DEFAULT;
    if (keep_src && (parse_bytes(keep_src, &keep) != 0 || keep == 0 || keep > 100000)) {
        fprintf(stderr, "run: keep '%.64s' is not a session count 1..100000\n", keep_src);
        return 2;
    }
    uint64_t hold_files = HOLD_QUOTA_FILES;
    if (hf_src && parse_bytes(hf_src, &hold_files) != 0) {
        fprintf(stderr, "run: hold file quota '%.64s' is not a count 0..%llu\n",
                hf_src, (unsigned long long)HOLD_QUOTA_CEIL);
        return 2;
    }

    char lp[1100];
    int lock_fd = -1;
    pid_t holder;
    if (sessions_path(lp, sizeof lp, NULL) || mkdirs(lp)) { fprintf(stderr, "run: no sessions dir\n"); return 1; }
    int lk = lock_take(&lock_fd, &holder);
    if (lk != 0) {
        if (lk == -1) fprintf(stderr, "run: world busy — another run holds sessions/LOCK (pid %d). no frames ran.\n", (int)holder);
        else fprintf(stderr, "run: cannot open sessions/LOCK. no frames ran.\n");
        return 7;
    }

    FILE *f = (script && strcmp(script, "-")) ? fopen(script, "r") : stdin;
    if (!f) { fprintf(stderr, "run: cannot open %s: %s\n", script, strerror(errno)); return 2; }
    static Instr prog[MAX_OPS];
    int nops = 0, ln = 0;
    char line[LINE_BYTES], err[256];
    const char *rule = "internal";
    while (fgets(line, sizeof line, f)) {
        ln++;
        if (!strchr(line, '\n') && !feof(f)) {
            fprintf(stderr, "FAULT line %d: line too long\n", ln);
            rule_say(stderr, "rule=line-long");
            return 1;
        }
        int r = parse_line(line, ln, &prog[nops < MAX_OPS ? nops : MAX_OPS - 1], err, sizeof err, &rule);
        if (r < 0) {
            char rl[48];
            fprintf(stderr, "FAULT line %d: %s\n", ln, err);
            snprintf(rl, sizeof rl, "rule=%s", rule);
            rule_say(stderr, rl);
            return 1;
        }
        if (r == 1 && ++nops > MAX_OPS) {
            fprintf(stderr, "FAULT line %d: script over %d ops\n", ln, MAX_OPS);
            rule_say(stderr, "rule=script-long");
            return 1;
        }
    }
    if (f != stdin) fclose(f);
    int pruned = retain((unsigned)keep);

    char id[64], dir[1024], path[1100], sdir[1024];
    snprintf(id, sizeof id, "%lld-%d", (long long)time(NULL), (int)getpid());
    if (sessions_path(sdir, sizeof sdir, NULL) || sessions_path(dir, sizeof dir, id) || mkdirs(dir)) {
        fprintf(stderr, "run: cannot create session dir\n");
        return 1;
    }
    /* log first, then the helper: a refused start leaves its reason in sessions/<id>/log,
       and no CURRENT, so status stays dark. */
    if (path_join(path, sizeof path, dir, "log")) return 1;
    g_log = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
    if (g_log < 0) return 1;
    char why[160], r[128];
    if (mb_open(&g_mb, dir, g_root, g_log, why, sizeof why) != 0) {
        dprintf(g_log, "MAILBOX fail: %s\n", why);
        fprintf(stderr, "run: %s — fail closed, no frames ran.\n", why);
        return 6;
    }
    dprintf(g_log, "RETAIN keep=%llu removed=%d\n", (unsigned long long)keep, pruned);
    int arm = mb_ask(&g_mb, "ARM_OK", NULL, r, sizeof r);
    if (arm != 1) {
        fprintf(stderr, "run: helper %s — %s, no frames ran.\n",
                arm < 0 ? "silent on ARM_OK" : "refused ARM_OK", arm < 0 ? "fail closed" : r);
        mb_close(&g_mb);
        return arm < 0 ? 6 : 5;
    }

    char text[4096] = "";
    snprintf(text, sizeof text, "%s\n", id);
    if (path_join(path, sizeof path, sdir, "CURRENT") || write_atomic(path, text)) return 1;
    snprintf(text, sizeof text, "%d\n", (int)getpid());
    if (path_join(path, sizeof path, dir, "PID") || write_atomic(path, text)) return 1;
    /* the opcode stream. replay is stream + snapshots. */
    text[0] = 0;
    for (int i = 0; i < nops; i++) {
        char one[700];
        fmt_instr(&prog[i], one, sizeof one);
        strncat(text, one, sizeof text - strlen(text) - 1);
    }
    if (path_join(path, sizeof path, dir, "OPS") || write_atomic(path, text)) return 1;

    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);

    static Session s;
    if (session_start(&s, g_root, dir, (uint32_t)n, (uint32_t)n, 0, 0, 0, hold_quota, hold_files)) {
        fprintf(stderr, "FAULT session start: snap s0 failed\n");
        return 1;
    }
    s.gate = run_gate;
    s.tok = tok;
    /* SESSION is frozen once frames start; the helper that answered is part of it. */
    if (path_join(path, sizeof path, dir, "SESSION") == 0) {
        int sf = open(path, O_WRONLY | O_APPEND | O_CLOEXEC);
        if (sf >= 0) { dprintf(sf, "helper=%s\n", HELPER_VERSION + strlen("helper ")); close(sf); }
    }
    dprintf(g_log, "ARM token %s dev=%llu ino=%llu\n", tok.path,
            (unsigned long long)tok.dev, (unsigned long long)tok.ino);

    int rc = 0;
    for (int i = 0; i < nops; i++) {
        if (s.n >= s.n_max) {
            /* the edge, before the work: N is a budget, not a suggestion */
            ev(&s, 1, "fault=over-N n=%u N=%u rule=over-n", s.n, s.n_max);
            s.out[0] = 0;
            s.bus.lamps = lamp_set(s.bus.lamps, LAMP_HOLD);
            snap(&s, "fault");
            session_state(&s, "fault");
            fprintf(stderr, "FAULT line %d: over N (%u)\n", prog[i].line, s.n_max);
            rule_say(stderr, s.ev);
            rc = 1;
            break;
        }
        s.ev[0] = 0;
        s.out[0] = 0;
        int k_due = ((s.n + 1) % s.k_snap) == 0;
        int fr = frame(&s, prog[i].op, TOOL[prog[i].op], &prog[i], k_due);
        if (fr > 0) {
            /* stopped at the gate: this op never ran and has no snap */
            session_state(&s, fr == 3 ? "halt" : fr == 5 ? "disarmed" : "fault");   /* 6: helper lost */
            fprintf(stderr, "HALT line %d: %s\n", prog[i].line, s.ev);
            rule_say(stderr, s.ev);
            rc = fr;
            break;
        }
        printf("frame %u %-5s snap=%s %s\n", s.n, OP_NAME[prog[i].op], s.snap_id, fr ? "FAULT" : "ok");
        if (g_halt) {
            /* KILL landed during the step: it was snapped; nothing after it runs */
            session_state(&s, "halt");
            rc = 3;
            break;
        }
        if (fr != 0 && s.tainted) {
            /* a TEST moved what it must only read: the board is suspect, the run is disarmed */
            session_state(&s, "disarmed");
            dprintf(g_log, "TAINT %s\n", s.ev);
            fprintf(stderr, "FAULT line %d: %s — disarmed\n", prog[i].line, s.ev);
            rule_say(stderr, s.ev);
            rc = 5;
            break;
        }
        if (fr != 0) {
            session_state(&s, "fault");
            fprintf(stderr, "FAULT line %d: %s\n", prog[i].line, s.ev);
            rule_say(stderr, s.ev);
            rc = 1;
            break;
        }
    }
    if (rc == 0) session_state(&s, "ok");
    mb_close(&g_mb);
    close(g_log);
    if (path_join(path, sizeof path, dir, "PID") == 0) unlink(path);
    fflush(stdout);
    cmd_status();
    return rc;
}

static int cmd_kill(void) {
    char dir[1024], id[128], path[1100], buf[1024], sn[32];
    /* a live demo is proven by its own lock, like a run by the world lock */
    pid_t demo = lock_holder_at("DEMO");
    if (demo > 0) { kill(demo, SIGTERM); printf("KILL demo pid %d\n", (int)demo); }
    if (current_dir(dir, sizeof dir, id, sizeof id)) {
        if (demo > 0) return 0;
        fprintf(stderr, "kill: no session\n");
        return 1;
    }
    if (path_join(path, sizeof path, dir, "KILL") || write_atomic(path, "KILL\n")) return 1;
    /* signal only the live run: the PID file must name the process holding the world lock.
       a PID file left by a crash names nobody we may signal — that number may be reused. */
    if (path_join(path, sizeof path, dir, "PID") == 0 && read_small(path, buf, sizeof buf) == 0) {
        pid_t pid = (pid_t)atoi(buf), holder = lock_holder();
        if (pid > 0 && holder == pid) kill(pid, SIGTERM);
        else if (pid > 0)
            printf("kill: pid %d does not hold the world lock (%s) — not signalled\n", (int)pid,
                   holder ? "another run holds it" : "no live run");
    }
    sn[0] = 0;
    if (path_join(path, sizeof path, dir, "STATE") == 0 && read_small(path, buf, sizeof buf) == 0)
        kv(buf, "snap", sn, sizeof sn);
    printf("KILL %s last snap %s\n", id, sn[0] ? sn : "-");
    return 0;
}

/* demo: one green light for the whole ROM. not a session and no frames, but inside reach:
   a lock (sessions/DEMO) proves its pid to `kill`, and its knife is T_tool per ROM test file
   rather than a flat five minutes. */
#define T_TOOL_DEMO_MS 5000u

static unsigned rom_files(void) {
    char p[1100];
    unsigned n = 0;
    if (path_join(p, sizeof p, g_root, "tests/rom")) return 0;
    DIR *d = opendir(p);
    if (!d) return 0;
    struct dirent *e;
    while ((e = readdir(d)) != NULL)
        if (prefix(e->d_name, "test_") && suffix(e->d_name, ".py")) n++;
    closedir(d);
    return n;
}

static int cmd_demo(void) {
    if (rom_ok() != 0) return 4;
    char sp[1100];
    int lock_fd = -1;
    pid_t holder;
    if (sessions_path(sp, sizeof sp, NULL) || mkdirs(sp)) return 1;
    if (lock_take_at("DEMO", &lock_fd, &holder) != 0) {
        fprintf(stderr, "demo: already running (pid %d)\n", (int)holder);
        return 7;
    }
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    unsigned roms = rom_files();
    uint32_t knife = T_TOOL_DEMO_MS * (roms ? roms : 1);
    fprintf(stderr, "demo: roms=%u knife=%ums\n", roms, knife);
    char *argv[] = {"python3", "tools/test_runner.py", NULL};
    char out[256] = "";
    int rc = child_run(g_root, argv, JAIL_NET_ONLY, out, sizeof out, NULL, knife, OUT_CEIL_BYTES, -1, -1);
    char *nl = strchr(out, '\n');
    if (nl) *nl = 0;
    if (rc == -3) { printf("HALT demo killed\n"); return 3; }
    if (rc == -2) { printf("RED knife>%ums\n", knife); return 1; }
    if (rc == -4) { printf("RED out>%u\n", OUT_CEIL_BYTES); return 1; }
    if (rc != 0) {
        printf("%s\n", prefix(out, "RED") ? out : "RED");
        return 1;
    }
    printf("%s\n", prefix(out, "GREEN") ? out : "RED");
    return prefix(out, "GREEN") ? 0 : 1;
}

/* ---- restore: resume = load snap ----
 * bench restore snap-<k> | <session>/snap-<k>
 * an owner command, not an intern op: armed, world locked, ROM crowned. the snap must hold a
 * board, and main/ (from the world) + hold/ (from the snap) must hash to its MANIFEST tree=
 * before anything moves. the old hold/ is kept in sessions/<new>/hold.before, never deleted.
 * the new session's s0 is the restored board. no frames run. */
static int cmd_restore(int argc, char **argv) {
    if (argc != 1) { fprintf(stderr, "usage: bench restore snap-<k> | <session>/snap-<k>\n"); return 2; }
    char sid[128], sname[32], cdir[1024];
    const char *arg = argv[0], *slash = strchr(arg, '/');
    if (slash) {
        size_t l = (size_t)(slash - arg);
        if (l == 0 || l >= sizeof sid) { fprintf(stderr, "restore: bad session in %s\n", arg); return 2; }
        memcpy(sid, arg, l);
        sid[l] = 0;
        snprintf(sname, sizeof sname, "%.31s", slash + 1);
    } else {
        if (current_dir(cdir, sizeof cdir, sid, sizeof sid)) { fprintf(stderr, "restore: no current session\n"); return 1; }
        snprintf(sname, sizeof sname, "%.31s", arg);
    }
    char *end;
    if (strncmp(sname, "snap-", 5) || !sname[5] || (strtoul(sname + 5, &end, 10), *end) ||
        strchr(sid, '/') || strstr(sid, "..") || sid[0] == '.') {
        fprintf(stderr, "restore: '%s' is not <session>/snap-<k>\n", arg);
        return 2;
    }
    if (rom_ok() != 0) return 4;
    TokenId tok;
    char tw[256];
    if (!arm_read(&tok, tw, sizeof tw)) { fprintf(stderr, "restore: not armed — %s\n", tw); return 5; }
    char lp[1100];
    int lock_fd = -1;
    pid_t holder;
    if (sessions_path(lp, sizeof lp, NULL) || mkdirs(lp)) return 1;
    if (lock_take(&lock_fd, &holder) != 0) {
        fprintf(stderr, "restore: world busy — sessions/LOCK held (pid %d)\n", (int)holder);
        return 7;
    }

    char odir[1024], snapdir[1100], man[1200], buf[2048], tree[80];
    if (sessions_path(odir, sizeof odir, sid) || path_join(snapdir, sizeof snapdir, odir, sname) ||
        path_join(man, sizeof man, snapdir, "MANIFEST") || read_small(man, buf, sizeof buf)) {
        fprintf(stderr, "restore: no snap %s/%s\n", sid, sname);
        return 1;
    }
    if (!kv(buf, "tree", tree, sizeof tree) || strlen(tree) != 64) {
        fprintf(stderr, "restore: %s/%s holds no board (tree=%s)\n", sid, sname, tree[0] ? tree : "?");
        return 1;
    }
    /* integrity first, independent of main/: the snap's stored hold must match board=. */
    char btree[80], bnow[65];
    const char *bp[] = {"hold"};
    if (kv(buf, "board", btree, sizeof btree) && strlen(btree) == 64) {
        if (tree_hash(snapdir, bp, 1, bnow) != 0 || strcmp(bnow, btree)) {
            fprintf(stderr, "restore: %s/%s stored hold is corrupt (board hash mismatch). nothing moved.\n",
                    sid, sname);
            return 1;
        }
    }
    const char *paths[] = {"main", "hold"};
    const char *from_snap[] = {g_root, snapdir};
    char hex[65];
    if (tree_hash_roots(from_snap, paths, 2, hex) != 0 || strcmp(hex, tree)) {
        fprintf(stderr, "restore: %s/%s does not hash to its MANIFEST tree (snap damaged, or main/ "
                        "changed since). nothing moved.\n", sid, sname);
        return 1;
    }

    char id[64], dir[1024], stage[1100], shold[1200], whold[1100], before[1100], src[1200], path[1100];
    snprintf(id, sizeof id, "%lld-%d", (long long)time(NULL), (int)getpid());
    if (sessions_path(dir, sizeof dir, id) || mkdirs(dir) || path_join(stage, sizeof stage, dir, "stage") ||
        mkdirs(stage) || path_join(shold, sizeof shold, stage, "hold") || path_join(src, sizeof src, snapdir, "hold") ||
        path_join(whold, sizeof whold, g_root, "hold") || path_join(before, sizeof before, dir, "hold.before"))
        return 1;
    if (mkdir(shold, 0755) != 0 || copy_board(src, shold) != 0) {
        fprintf(stderr, "restore: cannot stage the snap's hold/. nothing moved.\n");
        return 1;
    }
    const char *from_stage[] = {g_root, stage};
    if (tree_hash_roots(from_stage, paths, 2, hex) != 0 || strcmp(hex, tree)) {
        fprintf(stderr, "restore: staged copy does not match. nothing moved.\n");
        return 1;
    }
    if (rename(whold, before) != 0 && errno != ENOENT) {
        fprintf(stderr, "restore: cannot move hold/ aside: %s. nothing moved.\n", strerror(errno));
        return 1;
    }
    if (rename(shold, whold) != 0) {
        fprintf(stderr, "restore: cannot place the restored hold/: %s — putting the old one back\n", strerror(errno));
        rename(before, whold);
        return 1;
    }
    rmdir(stage);

    if (path_join(path, sizeof path, dir, "log")) return 1;
    g_log = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
    if (g_log >= 0) dprintf(g_log, "RESTORE %s/%s tree=%s old hold/ -> hold.before\n", sid, sname, tree);
    static Session s;
    if (session_start(&s, g_root, dir, N_MAX_DEFAULT, N_MAX_DEFAULT, 0, 0, 0,
                      HOLD_QUOTA_BYTES, HOLD_QUOTA_FILES) != 0) {
        fprintf(stderr, "restore: hold/ restored, but session s0 failed\n");
        return 1;
    }
    char s0[1200], m0[2048], t0[80];
    if (path_join(s0, sizeof s0, dir, "snap-0/MANIFEST") || read_small(s0, m0, sizeof m0) ||
        !kv(m0, "tree", t0, sizeof t0) || strcmp(t0, tree)) {
        fprintf(stderr, "restore: new s0 does not match the restored snap\n");
        return 1;
    }
    if (path_join(path, sizeof path, dir, "SESSION") == 0) {
        int sf = open(path, O_WRONLY | O_APPEND | O_CLOEXEC);
        if (sf >= 0) { dprintf(sf, "restored_from=%s/%s\n", sid, sname); close(sf); }
    }
    session_state(&s, "restored");
    char text[160], cur[1100];
    snprintf(text, sizeof text, "%s\n", id);
    if (sessions_path(cur, sizeof cur, "CURRENT") || write_atomic(cur, text)) return 1;
    printf("RESTORE %s/%s -> session %s s0 tree=%.12s (old hold/ kept in sessions/%s/hold.before)\n",
           sid, sname, id, tree, id);
    return 0;
}

/* ---- fork: a new world from a verified snapshot ----
 * bench fork snap-<k> | <session>/snap-<k> <new-world-dir>
 * an owner command, not an intern op. the snap's board= and tree= must check out before
 * anything is written. the new world gets copies (never hard links: a write in one world must
 * never reach another) of main/ tools/ isa/ tests/rom/ supervisor/woz_bus.h from this world and
 * hold/ from the snap,
 * empty proposed/ and tests/proposed/, and a fresh sessions/ holding only FORKED_FROM. the
 * supervisor binaries are used by path, not copied. it is NOT armed: no token is copied, the
 * owner arms it. it has its own sessions/LOCK, so worlds run in parallel. the new world is
 * checked (main/+hold/ against tree=, tests/rom against the crown) before fork says ok; on any
 * failure the half-built world is removed. */
static int cmd_fork(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: bench fork snap-<k> | <session>/snap-<k> <new-world-dir>\n"); return 2; }
    char sid[128], sname[32], cdir[1024];
    const char *arg = argv[0], *target = argv[1], *slash = strchr(arg, '/');
    if (slash) {
        size_t l = (size_t)(slash - arg);
        if (l == 0 || l >= sizeof sid) { fprintf(stderr, "fork: bad session in %s\n", arg); return 2; }
        memcpy(sid, arg, l);
        sid[l] = 0;
        snprintf(sname, sizeof sname, "%.31s", slash + 1);
    } else {
        if (current_dir(cdir, sizeof cdir, sid, sizeof sid)) { fprintf(stderr, "fork: no current session\n"); return 1; }
        snprintf(sname, sizeof sname, "%.31s", arg);
    }
    char *end;
    if (strncmp(sname, "snap-", 5) || !sname[5] || (strtoul(sname + 5, &end, 10), *end) ||
        strchr(sid, '/') || strstr(sid, "..") || sid[0] == '.') {
        fprintf(stderr, "fork: '%s' is not <session>/snap-<k>\n", arg);
        return 2;
    }
    if (!target[0]) { fprintf(stderr, "fork: empty target\n"); return 2; }
    struct stat st;
    if (lstat(target, &st) == 0) { fprintf(stderr, "fork: %s exists — a fork makes a new world, never into one\n", target); return 1; }

    /* a world inside this one would share its files through the back door: refuse. */
    char rroot[4096], tparent[4096], rparent[4096];
    const char *ts = strrchr(target, '/');
    if (ts == target) snprintf(tparent, sizeof tparent, "/");
    else if (ts) snprintf(tparent, sizeof tparent, "%.*s", (int)(ts - target), target);
    else snprintf(tparent, sizeof tparent, ".");
    if (!realpath(g_root, rroot) || !realpath(tparent, rparent)) {
        fprintf(stderr, "fork: cannot resolve %s or %s: %s\n", g_root, tparent, strerror(errno));
        return 1;
    }
    size_t rl = strlen(rroot);
    if (!strncmp(rparent, rroot, rl) && (rparent[rl] == 0 || rparent[rl] == '/' || rl == 1)) {
        fprintf(stderr, "fork: %s is inside this world — a fork lives beside it, not in it\n", target);
        return 2;
    }

    if (rom_ok() != 0) return 4;
    TokenId tok;
    char tw[256];
    if (!arm_read(&tok, tw, sizeof tw)) { fprintf(stderr, "fork: not armed — %s\n", tw); return 5; }

    char odir[1024], snapdir[1100], man[1200], buf[2048], tree[80], board[80], now[65];
    if (sessions_path(odir, sizeof odir, sid) || path_join(snapdir, sizeof snapdir, odir, sname) ||
        path_join(man, sizeof man, snapdir, "MANIFEST") || read_small(man, buf, sizeof buf)) {
        fprintf(stderr, "fork: no snap %s/%s\n", sid, sname);
        return 1;
    }
    if (!kv(buf, "tree", tree, sizeof tree) || strlen(tree) != 64 ||
        !kv(buf, "board", board, sizeof board) || strlen(board) != 64) {
        fprintf(stderr, "fork: %s/%s holds no board — nothing to fork from\n", sid, sname);
        return 1;
    }
    const char *bp[] = {"hold"}, *mh[] = {"main", "hold"};
    if (tree_hash(snapdir, bp, 1, now) != 0 || strcmp(now, board)) {
        fprintf(stderr, "fork: %s/%s stored hold is corrupt (board hash mismatch). nothing written.\n", sid, sname);
        return 1;
    }
    const char *from_snap[] = {g_root, snapdir};
    if (tree_hash_roots(from_snap, mh, 2, now) != 0 || strcmp(now, tree)) {
        fprintf(stderr, "fork: %s/%s does not hash to its MANIFEST tree (main/ changed since). nothing written.\n",
                sid, sname);
        return 1;
    }

    /* claim the target: mkdir fails if anything got there first. from here, failure removes it. */
    if (mkdir(target, 0755) != 0) { fprintf(stderr, "fork: cannot create %s: %s\n", target, strerror(errno)); return 1; }
    uint64_t t0 = nowns();
    char src[1200], dst[4200];
    /* supervisor/woz_bus.h: the one lamp-byte definition tools/peek.py reads. binaries stay by path. */
    static const char *const FROM_WORLD[] = {"main", "tools", "isa", "tests/rom", "supervisor/woz_bus.h"};
    static const char *const EMPTY[] = {"tests", "proposed", "tests/proposed", "sessions", "supervisor"};
    int bad = 0;
    for (size_t i = 0; !bad && i < sizeof EMPTY / sizeof *EMPTY; i++)
        bad = snprintf(dst, sizeof dst, "%s/%s", target, EMPTY[i]) >= (int)sizeof dst || mkdir(dst, 0755) != 0;
    for (size_t i = 0; !bad && i < sizeof FROM_WORLD / sizeof *FROM_WORLD; i++)
        bad = path_join(src, sizeof src, g_root, FROM_WORLD[i]) ||
              snprintf(dst, sizeof dst, "%s/%s", target, FROM_WORLD[i]) >= (int)sizeof dst ||
              copy_board(src, dst) != 0;
    if (!bad)
        bad = path_join(src, sizeof src, snapdir, "hold") ||
              snprintf(dst, sizeof dst, "%s/hold", target) >= (int)sizeof dst ||
              copy_board(src, dst) != 0 || (mkdir(dst, 0755) != 0 && errno != EEXIST);
    if (!bad) {
        const char *rp[] = {"tests/rom"};
        char rom[65];
        if (tree_hash(target, mh, 2, now) != 0 || strcmp(now, tree)) {
            fprintf(stderr, "fork: new world does not hash to the snap's tree. removed.\n");
            bad = 1;
        } else if (strcmp(ROM_HASH, "UNPINNED") && (tree_hash(target, rp, 1, rom) != 0 || strcmp(rom, ROM_HASH))) {
            fprintf(stderr, "fork: new world's tests/rom does not match the crown. removed.\n");
            bad = 1;
        }
    }
    if (!bad) {
        char text[1400];
        snprintf(text, sizeof text, "forked_from=%s/sessions/%s/%s\ntree=%s\nboard=%s\n", rroot, sid, sname, tree, board);
        bad = snprintf(dst, sizeof dst, "%s/sessions/FORKED_FROM", target) >= (int)sizeof dst || write_atomic(dst, text);
    }
    if (bad) {
        if (errno) fprintf(stderr, "fork: building %s failed: %s. removed.\n", target, strerror(errno));
        rm_tree(target);
        return 1;
    }
    printf("FORK %s/%s -> %s tree=%.12s ms=%.1f (not armed: the owner arms it)\n", sid, sname, target, tree,
           (double)(nowns() - t0) / 1e6);
    return 0;
}

static int cmd_snap_ls(void) {
    char dir[1024], id[128];
    if (current_dir(dir, sizeof dir, id, sizeof id)) { fprintf(stderr, "snap-ls: no session\n"); return 1; }
    for (unsigned k = 0;; k++) {
        char name[32], path[1100], man[1100], buf[1024], sn[32], why[32], tree[80];
        snprintf(name, sizeof name, "snap-%u", k);
        if (path_join(path, sizeof path, dir, name) || path_join(man, sizeof man, path, "MANIFEST")) break;
        if (read_small(man, buf, sizeof buf)) break;
        kv(buf, "snap", sn, sizeof sn);
        kv(buf, "why", why, sizeof why);
        kv(buf, "tree", tree, sizeof tree);
        printf("%s/%-8s %s %-5s %.12s\n", id, name, sn, why, tree);
    }
    return 0;
}

/* verify a snapshot's stored board against the hash it recorded: content-addressed, so it
   catches a mutation of any (possibly shared) inode regardless of who made it — root, a tool,
   bit rot. `bench verify [snap-<k> | <session>/snap-<k>]`, or no arg for every snap of the
   current session. 0 all intact · 1 a mismatch or a damaged snap · 2 usage. */
static int verify_one(const char *sdir, const char *sname, int *checked, int *noboard) {
    char man[1200], buf[2048], want[80], now[65];
    const char *hp[] = {"hold"};
    char snapdir[1100];
    if (path_join(snapdir, sizeof snapdir, sdir, sname) || path_join(man, sizeof man, snapdir, "MANIFEST"))
        return -1;
    if (read_small(man, buf, sizeof buf)) { fprintf(stderr, "verify: %s has no MANIFEST\n", sname); return 1; }
    if (!kv(buf, "board", want, sizeof want) || !strcmp(want, "none")) { (*noboard)++; return 0; }
    if (tree_hash(snapdir, hp, 1, now) != 0) { fprintf(stderr, "verify: cannot hash %s/hold\n", sname); return 1; }
    (*checked)++;
    if (strcmp(want, now) != 0) {
        printf("VERIFY %s MISMATCH board stored=%.12s now=%.12s\n", sname, want, now);
        return 1;
    }
    return 0;
}

static int cmd_verify(int argc, char **argv) {
    if (argc > 1) { fprintf(stderr, "usage: bench verify [snap-<k> | <session>/snap-<k>]\n"); return 2; }
    char sid[128], sdir[1024], cdir[1024];
    const char *one = NULL, *arg = argc == 1 ? argv[0] : NULL;
    char sname[32] = "";
    if (arg) {
        const char *slash = strchr(arg, '/');
        if (slash) {
            size_t l = (size_t)(slash - arg);
            if (l == 0 || l >= sizeof sid) { fprintf(stderr, "verify: bad session in %s\n", arg); return 2; }
            memcpy(sid, arg, l); sid[l] = 0;
            snprintf(sname, sizeof sname, "%.31s", slash + 1);
        } else {
            if (current_dir(cdir, sizeof cdir, sid, sizeof sid)) { fprintf(stderr, "verify: no current session\n"); return 1; }
            snprintf(sname, sizeof sname, "%.31s", arg);
        }
        char *end;
        if (strncmp(sname, "snap-", 5) || !sname[5] || (strtoul(sname + 5, &end, 10), *end) ||
            strchr(sid, '/') || strstr(sid, "..") || sid[0] == '.') {
            fprintf(stderr, "verify: '%s' is not <session>/snap-<k>\n", arg);
            return 2;
        }
        one = sname;
    } else if (current_dir(cdir, sizeof cdir, sid, sizeof sid)) {
        fprintf(stderr, "verify: no current session\n");
        return 1;
    }
    if (sessions_path(sdir, sizeof sdir, sid)) return 1;

    int checked = 0, noboard = 0, rc = 0;
    if (one) {
        rc = verify_one(sdir, one, &checked, &noboard);
    } else {
        for (unsigned k = 0;; k++) {
            char name[32], probe[1200];
            struct stat st;
            snprintf(name, sizeof name, "snap-%u", k);
            if (path_join(probe, sizeof probe, sdir, name) || lstat(probe, &st) != 0) break;
            int r = verify_one(sdir, name, &checked, &noboard);
            if (r != 0) { rc = r; break; }
        }
    }
    if (rc == 0) printf("VERIFY %s ok checked=%d noboard=%d\n", sid, checked, noboard);
    return rc;
}

int main(int argc, char **argv) {
    const char *r = getenv("BENCH_ROOT");
    if (r && *r) g_root = r;
    if (argc < 2) goto usage;
    if (!strcmp(argv[1], "status")) {
        if (argc == 3 && !strcmp(argv[2], "--line")) return cmd_status_line();
        if (argc != 2) goto usage;
        return cmd_status();
    }
    if (!strcmp(argv[1], "run")) return cmd_run(argc - 2, argv + 2);
    if (!strcmp(argv[1], "kill")) return cmd_kill();
    if (!strcmp(argv[1], "demo")) return cmd_demo();
    if (!strcmp(argv[1], "snap-ls")) return cmd_snap_ls();
    if (!strcmp(argv[1], "restore")) return cmd_restore(argc - 2, argv + 2);
    if (!strcmp(argv[1], "verify")) return cmd_verify(argc - 2, argv + 2);
    if (!strcmp(argv[1], "fork")) return cmd_fork(argc - 2, argv + 2);
    if (!strcmp(argv[1], "rules") && argc == 2) {
        /* the refusal table, one rule per line: what the ROM mirror is checked against */
        for (unsigned i = 0; i < RULES_N; i++) printf("rule=%s fix: %s\n", RULES[i].id, RULES[i].fix);
        return 0;
    }
usage:
    fprintf(stderr, "usage: bench status [--line] | run [--n N] [--hold-quota BYTES] [--hold-files N] [script|-]"
                    " | kill | demo | snap-ls | restore snap-<k> | verify [snap-<k>] | fork snap-<k> <dir> | rules\n");
    return 2;
}
