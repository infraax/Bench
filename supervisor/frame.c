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
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "frame.h"
#include "sha256.h"

/* one clock. escape and slowness are both measured on the monotonic line;
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
        if ((nowns() - t0) / 1000000ull > timeout_ms) {
            /* the knife */
            kill(pid, SIGKILL);
            if (!done) waitpid(pid, &st, 0);
            close(p[0]);
            if (out) out[used] = 0;
            if (nbytes) *nbytes = total;
            return -2;
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

/* always snapshot, then decide if that snap is worth keeping on a cadence.
   skipping the write because "nothing changed" is how hidden state is born.
   hash tree -> manifest -> atomic rename. */
int snap(Session *s, const char *why) {
    char hash[65] = "", tmp[1024], fin[1024], name[64], path[1100], man[1024];
    /* hash the board in C. no interpreter boot inside the frame. */
    const char *paths[] = {"main", "hold"};
    if (tree_hash(s->root, paths, 2, hash) != 0) return -1;

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
    if (copy_tree(src, dst) != 0) return -1;

    if (rename(tmp, fin) != 0) return -1;
    s->k = k + 1;
    memcpy(s->snap_id, id, sizeof id);
    s->last_snap_ns = nowns();
    return session_state(s, "run");
}

/* one frame. intern op already parsed and checked upstairs.
   two clocks: the tool child has already spent T_tool inside child_run (its own knife);
   here we measure only the C thread's own work (snap + bookkeeping) against T_frame,
   and the whole session against T_session. python boot is not the frame.
   return: 0 ok, 1 halt, -1 fault. */
int frame(Session *s, Op op, Tool tool, void *arg, int k_due) {
    uint64_t tool_t0 = nowns();
    int rc = 0;

    /* do always. the tool is a child with its own timeout; that time is not the frame. */
    if (tool) rc = tool(s, arg);
    uint64_t tool_ms = (nowns() - tool_t0) / 1000000ull;

    uint64_t c0 = nowns();   /* the C thread's own work starts here */
    size_t l = strlen(s->ev);
    snprintf(s->ev + l, sizeof s->ev - l, " tool_ms=%llu", (unsigned long long)tool_ms);
    s->n++;
    if (snap(s, "step") != 0) {
        /* no snapshot, no step. worst-case: n does not advance on a missed frame. */
        s->n--;
        s->bus.lamps = lamp_set(s->bus.lamps, LAMP_HOLD);
        return -1;
    }

    /* then inhibit */
    if (rc != 0) { s->bus.lamps = lamp_set(s->bus.lamps, LAMP_HOLD); return -1; }
    if ((nowns() - c0) / 1000000ull > s->t_step_ms) return -1;              /* T_frame */
    if ((nowns() - s->t0_ns) / 1000000ull > s->t_sess_ms) return -1;       /* T_session */
    if (s->n > s->n_max) return -1;
    if (k_due && snap(s, "K") != 0) return -1;
    (void)op;
    return 0;
}

int session_start(Session *s, const char *root, const char *dir,
                  uint32_t n, uint32_t k, uint32_t ts, uint32_t tt, uint32_t tS) {
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

    /* radio off by default. no eyes, no judge. fs and tty wired. */
    s->bus.plug = (uint8_t)((1u << SLOT_N) - 1);
    pull(&s->bus, SLOT_RADIO);
    pull(&s->bus, SLOT_FB);
    pull(&s->bus, SLOT_JUDGE);
    s->bus.cap[SLOT_FS] = 4096;
    s->bus.cap[SLOT_TTY] = 4096;
    s->bus.lamps = lamp_set(s->bus.lamps, LAMP_HOLD); /* long notch starts in hold. main is a promotion. */

    /* frozen for the session. changing these is a new session. */
    char path[1024], text[256];
    if (mkdirs(dir) || path_join(path, sizeof path, dir, "SESSION")) return -1;
    snprintf(text, sizeof text,
             "N_max=%u\nK=%u\nT_frame_ms=%u\nT_tool_ms=%u\nT_session_ms=%u\nplug=0x%02x\n",
             s->n_max, s->k_snap, s->t_step_ms, s->t_tool_ms, s->t_sess_ms, s->bus.plug);
    if (write_atomic(path, text)) return -1;
    return snap(s, "s0");
}
