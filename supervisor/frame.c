#define _GNU_SOURCE
/* frame.c — one step is a frame. if it has no edges it is a chat.
 *
 * the intern does not live here. this thread owns time.
 * tools are children with a knife. resume loads a snap, not a conversation.
 *
 * do the work, then inhibit. don't skip the snap on the happy path
 * and discover you missed a frame when hold/ has been running since tuesday.
 */
#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "frame.h"
#include "sha256.h"

volatile sig_atomic_t g_halt;

/* one clock. overrun and slowness are both measured on the monotonic line;
   a wall-clock warp (settimeofday) must not move a budget. */
uint64_t nowns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec*1000000000ull + (uint64_t)t.tv_nsec;
}

int path_join(char *out, size_t n, const char *a, const char *b) {
    int w = snprintf(out, n, "%s/%s", a, b);
    return (w < 0 || (size_t)w >= n) ? -1 : 0;
}

int mkdirs(const char *path) {
    char p[1024];
    size_t len = strlen(path);
    if (len == 0 || len >= sizeof p) return -1;
    memcpy(p, path, len + 1);
    for (char *c = p + 1; *c; c++) {
        if (*c != '/') continue;
        *c = 0;
        if (mkdir(p, 0755) != 0 && errno != EEXIST) return -1;
        *c = '/';
    }
    return (mkdir(p, 0755) != 0 && errno != EEXIST) ? -1 : 0;
}

int write_atomic(const char *path, const char *text) {
    char tmp[1100];
    if (snprintf(tmp, sizeof tmp, "%s.tmp", path) >= (int)sizeof tmp) return -1;
    FILE *f = fopen(tmp, "w");
    if (!f) return -1;
    int bad = fputs(text, f) < 0;
    bad |= fclose(f) != 0;
    if (bad) { unlink(tmp); return -1; }
    return rename(tmp, path);
}

int child_run(const char *root, char *const argv[], Jail jail, char *out, size_t outsz,
              uint64_t *nbytes, uint32_t timeout_ms, int log_fd, int err_fd) {
    int p[2];
    if (pipe(p) != 0) return -1;
    pid_t pid = fork();
    if (pid < 0) { close(p[0]); close(p[1]); return -1; }
    if (pid == 0) {
        int nul = open("/dev/null", O_RDONLY);
        if (nul >= 0) { dup2(nul, 0); close(nul); }
        dup2(p[1], 1);
        close(p[0]); close(p[1]);
        if (err_fd >= 0) dup2(err_fd, 2);
        if (chdir(root) != 0) _exit(126);
        /* drop authority, fail closed: a child that cannot be jailed does not run. */
        char **env = tool_env();
        if (!env || sandbox_apply(jail) != 0) _exit(125);
        execvpe(argv[0], argv, env);
        _exit(127);
    }
    close(p[1]);
    fcntl(p[0], F_SETFL, O_NONBLOCK);

    size_t used = 0;
    uint64_t total = 0, t0 = nowns();
    int st = 0, done = 0, eof = 0, rc;
    for (;;) {
        char buf[4096];
        ssize_t r;
        while ((r = read(p[0], buf, sizeof buf)) > 0) {
            total += (uint64_t)r;
            if (log_fd >= 0 && write(log_fd, buf, (size_t)r) < 0) { /* log is best-effort */ }
            if (out && used + 1 < outsz) {
                size_t c = (size_t)r < outsz - 1 - used ? (size_t)r : outsz - 1 - used;
                memcpy(out + used, buf, c);
                used += c;
            }
        }
        if (r == 0) eof = 1;
        if (!done && waitpid(pid, &st, WNOHANG) == pid) done = 1;
        if (done && eof) break;
        int late = (nowns() - t0) / 1000000ull > timeout_ms;
        if (late || g_halt) {
            /* the knife: on timeout, and on KILL — no child outlives the halt by T_tool */
            kill(pid, SIGKILL);
            if (!done) waitpid(pid, &st, 0);
            close(p[0]);
            if (out) out[used] = 0;
            if (nbytes) *nbytes = total;
            return late ? -2 : -3;
        }
        struct timespec ts = {0, 1000000};
        nanosleep(&ts, NULL);
    }
    close(p[0]);
    if (out) out[used] = 0;
    if (nbytes) *nbytes = total;
    rc = WIFEXITED(st) ? WEXITSTATUS(st) : -1;
    return rc;
}

static int copy_file(const char *src, const char *dst) {
    int in = open(src, O_RDONLY), out, rc = 0;
    if (in < 0) return -1;
    out = open(dst, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (out < 0) { close(in); return -1; }
    char buf[8192];
    ssize_t r;
    while ((r = read(in, buf, sizeof buf)) > 0)
        if (write(out, buf, (size_t)r) != r) { rc = -1; break; }
    if (r < 0) rc = -1;
    close(in);
    if (close(out) != 0) rc = -1;
    return rc;
}

/* photograph the board: regular files and dirs. links and devices are not board state. */
static int copy_tree(const char *src, const char *dst) {
    struct stat st;
    if (lstat(src, &st) != 0) return errno == ENOENT ? 0 : -1;
    if (S_ISREG(st.st_mode)) return copy_file(src, dst);
    if (!S_ISDIR(st.st_mode)) return 0;
    if (mkdir(dst, 0755) != 0 && errno != EEXIST) return -1;
    DIR *d = opendir(src);
    if (!d) return -1;
    int rc = 0;
    struct dirent *e;
    while (rc == 0 && (e = readdir(d)) != NULL) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char s2[1024], d2[1024];
        if (path_join(s2, sizeof s2, src, e->d_name) || path_join(d2, sizeof d2, dst, e->d_name)) rc = -1;
        else rc = copy_tree(s2, d2);
    }
    closedir(d);
    return rc;
}

int tree_bytes(const char *path, uint64_t *out) {
    struct stat st;
    if (lstat(path, &st) != 0) return errno == ENOENT ? 0 : -1;
    if (S_ISREG(st.st_mode)) { *out += (uint64_t)st.st_size; return 0; }
    if (!S_ISDIR(st.st_mode)) return 0;
    DIR *d = opendir(path);
    if (!d) return -1;
    int rc = 0;
    struct dirent *e;
    while (rc == 0 && (e = readdir(d)) != NULL) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        char p[1024];
        rc = path_join(p, sizeof p, path, e->d_name) ? -1 : tree_bytes(p, out);
    }
    closedir(d);
    return rc;
}

static int hold_bytes(const Session *s, uint64_t *out) {
    char p[1024];
    *out = 0;
    return path_join(p, sizeof p, s->root, "hold") ? -1 : tree_bytes(p, out);
}

int session_state(const Session *s, const char *status) {
    char path[1024], text[1200];
    const char *id = strrchr(s->dir, '/');
    id = id ? id + 1 : s->dir;
    if (path_join(path, sizeof path, s->dir, "STATE")) return -1;
    snprintf(text, sizeof text,
             "session=%s\nstatus=%s\nsnap=%s\nn=%u\nN=%u\nK=%u\nlamps=0x%02x\nplug=0x%02x\npeek=0x%02x\n",
             id, status, s->snap_id, s->n, s->n_max, s->k_snap,
             s->bus.lamps, s->bus.plug, peek(&s->bus));
    return write_atomic(path, text);
}

/* ---- TEST post-conditions ----
 * a pure test reads the board; it does not change it. whatever its source said, a TEST
 * step that moved main/ or tests/rom/, or created, replaced or touched the owner token,
 * is a fault. the token is checked raw (any file at the path), not by the arm rule. */

typedef struct { int exists; dev_t dev; ino_t ino; struct timespec mtime; off_t size; } Raw;

static void raw_stat(const char *p, Raw *r) {
    struct stat st;
    memset(r, 0, sizeof *r);
    if (!p || !*p || lstat(p, &st) != 0) return;
    r->exists = 1;
    r->dev = st.st_dev;
    r->ino = st.st_ino;
    r->mtime = st.st_mtim;
    r->size = st.st_size;
}

static int raw_same(const Raw *a, const Raw *b) {
    return a->exists == b->exists && (!a->exists ||
           (a->dev == b->dev && a->ino == b->ino && a->size == b->size &&
            a->mtime.tv_sec == b->mtime.tv_sec && a->mtime.tv_nsec == b->mtime.tv_nsec));
}

typedef struct { char main_h[65], rom_h[65]; Raw tok, env; } Board;

static int board_read(const Session *s, Board *b) {
    const char *m[] = {"main"}, *r[] = {"tests/rom"};
    char tp[1024];
    if (tree_hash(s->root, m, 1, b->main_h) || tree_hash(s->root, r, 1, b->rom_h)) return -1;
    if (path_join(tp, sizeof tp, s->root, TOKEN_REL)) return -1;
    raw_stat(tp, &b->tok);
    raw_stat(getenv("BENCH_TOKEN"), &b->env);
    return 0;
}

/* the token a TEST step touched is not the owner's any more: move it aside, never delete it. */
static void quarantine_token(const Session *s) {
    char tp[1024], q[1200];
    const char *id = strrchr(s->dir, '/');
    id = id ? id + 1 : s->dir;
    if (path_join(tp, sizeof tp, s->root, TOKEN_REL)) return;
    if (snprintf(q, sizeof q, "%s.tainted-%.64s", tp, id) >= (int)sizeof q) return;
    if (rename(tp, q) != 0 && errno != ENOENT) { /* the gate still refuses: token_same fails */ }
}

/* always snapshot, then decide if that snap is worth keeping on a cadence.
   skipping the write because "nothing changed" is how hidden state is born.
   hash tree -> manifest -> atomic rename.
   skip != NULL is for a step whose board must not be kept (over quota, or a TEST that broke
   its post-conditions): manifest and evidence are written, the board is not hashed or copied,
   and tree= says why. the last good board is the snap before. */
static int snap_board(Session *s, const char *why, const char *skip) {
    char hash[65], tmp[1024], fin[1024], name[64], path[1100], man[1024];
    int board = skip == NULL;
    snprintf(hash, sizeof hash, "skipped:%s", board ? "" : skip);
    /* hash the board in C. no interpreter boot inside the frame. */
    const char *paths[] = {"main", "hold"};
    if (board && tree_hash(s->root, paths, 2, hash) != 0) return -1;

    uint32_t k = s->k;
    snprintf(name, sizeof name, "snap-%u", k);
    if (path_join(fin, sizeof fin, s->dir, name)) return -1;
    if (snprintf(tmp, sizeof tmp, "%s.tmp", fin) >= (int)sizeof tmp) return -1;
    if (mkdir(tmp, 0755) != 0) return -1;

    char id[24];
    snprintf(id, sizeof id, "%03u-%08x", k, (unsigned)(nowns() & 0xffffffffu));
    snprintf(man, sizeof man,
             "snap=%s\nwhy=%s\nn=%u\nN_max=%u\nK=%u\nT_step_ms=%u\nT_session_ms=%u\n"
             "caps=fs:%u,tty:%u,fb:%u,judge:%u,radio:%u\nlamps=0x%02x\nplug=0x%02x\ntree=%s\nevidence=%s\n",
             id, why, s->n, s->n_max, s->k_snap, s->t_step_ms, s->t_sess_ms,
             s->bus.cap[SLOT_FS], s->bus.cap[SLOT_TTY], s->bus.cap[SLOT_FB],
             s->bus.cap[SLOT_JUDGE], s->bus.cap[SLOT_RADIO],
             s->bus.lamps, s->bus.plug, hash, s->ev[0] ? s->ev : "none");
    if (path_join(path, sizeof path, tmp, "MANIFEST") || write_atomic(path, man)) return -1;

    char src[1024], dst[1100];
    if (path_join(src, sizeof src, s->root, "hold") || path_join(dst, sizeof dst, tmp, "hold")) return -1;
    if (board && copy_tree(src, dst) != 0) return -1;

    if (rename(tmp, fin) != 0) return -1;
    s->k = k + 1;
    memcpy(s->snap_id, id, sizeof id);
    s->last_snap_ns = nowns();
    return session_state(s, "run");
}

int snap(Session *s, const char *why) { return snap_board(s, why, NULL); }

/* append a fault reason to the evidence line, after the tool's own words. */
static int fault(Session *s, const char *fmt, ...) {
    size_t l = strlen(s->ev);
    char why[96];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(why, sizeof why, fmt, ap);
    va_end(ap);
    snprintf(s->ev + l, sizeof s->ev - l, " %s", why);
    s->bus.lamps = lamp_set(s->bus.lamps, LAMP_HOLD);
    return -1;
}

/* one frame. intern op already parsed and checked upstairs.
   gate -> tool -> quota -> snap -> inhibit. the gate runs first: a stop there is no step.
   two clocks: the tool child has already spent T_tool inside child_run (its own knife);
   T_frame is the C thread's own work — gate, quota walk, snap, bookkeeping — and nothing
   else owns it. the whole session is measured against T_session. python boot is not the frame.
   return: 0 ok, >0 stopped at the gate (the exit code), -1 fault (snapped, then stopped). */
int frame(Session *s, Op op, Tool tool, void *arg, int k_due) {
    uint64_t g0 = nowns();
    if (s->gate) {
        int g = s->gate(s);
        if (g > 0) return g;
    }
    Board pre, post;
    if (op == OP_TEST && board_read(s, &pre) != 0) return fault(s, "fault=board-unreadable");
    uint64_t gate_ns = nowns() - g0;   /* gate + pre-step board read: the C thread's own work */
    int rc = 0;
    const char *skip = NULL;

    /* do always. the tool is a child with its own timeout; that time is not the frame. */
    uint64_t tool_t0 = nowns();
    if (tool) rc = tool(s, arg);
    uint64_t tool_ms = (nowns() - tool_t0) / 1000000ull;
    uint64_t c0 = nowns() - gate_ns;   /* T_frame: the gate's time counts, the tool's does not */

    /* TEST post-conditions: checked whatever the tool's rc, before the quota. */
    if (op == OP_TEST) {
        char moved[48] = "";
        if (board_read(s, &post) != 0) snprintf(moved, sizeof moved, "unreadable");
        else {
            if (strcmp(pre.main_h, post.main_h)) strcat(moved, "main,");
            if (strcmp(pre.rom_h, post.rom_h)) strcat(moved, "rom,");
            if (!raw_same(&pre.tok, &post.tok) || !raw_same(&pre.env, &post.env)) strcat(moved, "token,");
            size_t ml = strlen(moved);
            if (ml) moved[ml - 1] = 0;
        }
        if (moved[0]) {
            snprintf(s->ev, sizeof s->ev, "fault=test-postcondition moved=%s", moved);
            if (strstr(moved, "token")) quarantine_token(s);
            s->tainted = 1;
            skip = "tainted";
            rc = 1;
        }
    }

    /* hold quota: a successful tool that grew hold/ past budget is a failed step. */
    if (rc == 0 && !skip) {
        uint64_t hb;
        if (hold_bytes(s, &hb) != 0) {
            snprintf(s->ev, sizeof s->ev, "fault=hold-unreadable");
            rc = 1;
        } else if (hb > s->hold_base && hb - s->hold_base > s->hold_quota) {
            snprintf(s->ev, sizeof s->ev, "fault=hold-quota grew=%llu quota=%llu",
                     (unsigned long long)(hb - s->hold_base), (unsigned long long)s->hold_quota);
            rc = 1;
            skip = "over-quota";
        }
    }

    size_t l = strlen(s->ev);
    snprintf(s->ev + l, sizeof s->ev - l, " tool_ms=%llu", (unsigned long long)tool_ms);
    s->n++;
    if (snap_board(s, "step", skip) != 0) {
        /* no snapshot, no step. worst-case: n does not advance on a missed frame. */
        s->n--;
        return fault(s, "fault=snap n=%u", s->n);
    }

    /* then inhibit */
    if (rc != 0) { s->bus.lamps = lamp_set(s->bus.lamps, LAMP_HOLD); return -1; }
    uint64_t c_ms = (nowns() - c0) / 1000000ull, t_ms = (nowns() - s->t0_ns) / 1000000ull;
    if (c_ms > s->t_step_ms)
        return fault(s, "fault=T_frame ms=%llu>%u", (unsigned long long)c_ms, s->t_step_ms);
    if (t_ms > s->t_sess_ms)
        return fault(s, "fault=T_session ms=%llu>%u", (unsigned long long)t_ms, s->t_sess_ms);
    if (s->n > s->n_max) return fault(s, "fault=over-N n=%u>%u", s->n, s->n_max);
    if (k_due && snap(s, "K") != 0) return fault(s, "fault=snap-K n=%u", s->n);
    (void)op;
    return 0;
}

int session_start(Session *s, const char *root, const char *dir,
                  uint32_t n, uint32_t k, uint32_t ts, uint32_t tt, uint32_t tS, uint64_t hq) {
    memset(s, 0, sizeof *s);
    s->n_max = n ? n : N_MAX_DEFAULT;
    s->k_snap = k ? k : 1;
    /* snap is a C hash now, so the frame is tens of ms again, not five seconds. */
    s->t_step_ms = ts ? ts : 200;    /* T_frame: C-owned work per step */
    s->t_tool_ms = tt ? tt : 5000;   /* T_tool: a child's wall clock (python boot lives here) */
    s->t_sess_ms = tS ? tS : 60000;
    s->t0_ns = nowns();
    snprintf(s->root, sizeof s->root, "%s", root);
    snprintf(s->dir, sizeof s->dir, "%s", dir);
    s->hold_quota = hq;
    if (hold_bytes(s, &s->hold_base) != 0) return -1;

    /* radio off by default. no eyes, no judge. fs and tty wired. */
    s->bus.plug = (uint8_t)((1u << SLOT_N) - 1);
    pull(&s->bus, SLOT_RADIO);
    pull(&s->bus, SLOT_FB);
    pull(&s->bus, SLOT_JUDGE);
    s->bus.cap[SLOT_FS] = 4096;
    s->bus.cap[SLOT_TTY] = 4096;
    s->bus.lamps = lamp_set(s->bus.lamps, LAMP_HOLD); /* long notch starts in hold. main is a promotion. */

    /* frozen for the session. changing these is a new session. */
    char path[1024], text[384];
    if (mkdirs(dir) || path_join(path, sizeof path, dir, "SESSION")) return -1;
    snprintf(text, sizeof text,
             "N_max=%u\nK=%u\nT_frame_ms=%u\nT_tool_ms=%u\nT_session_ms=%u\nplug=0x%02x\n"
             "hold_quota=%llu\nhold_base=%llu\n",
             s->n_max, s->k_snap, s->t_step_ms, s->t_tool_ms, s->t_sess_ms, s->bus.plug,
             (unsigned long long)s->hold_quota, (unsigned long long)s->hold_base);
    if (write_atomic(path, text)) return -1;
    return snap(s, "s0");
}
