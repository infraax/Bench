/* main.c — bench: run | kill | demo | snap-ls | status
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
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "arm.h"
#include "frame.h"
#include "mailbox.h"
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

#define FAULT(...) do { snprintf(err, errsz, __VA_ARGS__); return -1; } while (0)

/* 1 = instruction, 0 = blank/comment, -1 = fault */
static int parse_line(char *ln, int lineno, Instr *in, char *err, size_t errsz) {
    ln[strcspn(ln, "\r\n")] = 0;
    char *p = ln;
    while (*p == ' ' || *p == '\t') p++;
    if (!*p || *p == '#') return 0;   /* chat is a comment track */

    memset(in, 0, sizeof *in);
    in->line = lineno;
    char *verb = tok(&p);
    for (size_t i = 0; i < sizeof SUPER_NAME / sizeof *SUPER_NAME; i++)
        if (!strcasecmp(verb, SUPER_NAME[i])) FAULT("%s is supervisor; intern emitting it is a spec bug", SUPER_NAME[i]);

    int op = 0;
    for (int i = OP_READ; i <= OP_WAIT; i++) if (!strcasecmp(verb, OP_NAME[i])) op = i;
    if (!op) FAULT("unknown verb '%.64s' (five: READ WRITE EXEC TEST WAIT)", verb);
    in->op = (Op)op;

    char *a = tok(&p), *b;
    switch (in->op) {
    case OP_READ:
    case OP_WRITE:
        b = tok(&p);
        if (!a || !b) FAULT("%s needs <slot> <path>", OP_NAME[op]);
        if (copy_field(in->slot, sizeof in->slot, a) || copy_field(in->path, sizeof in->path, b)) FAULT("field too long");
        if (!safe_rel(in->path)) FAULT("path escapes the world: %.160s", in->path);
        if (in->op == OP_READ && *trim(p)) FAULT("READ takes no payload");
        if (in->op == OP_WRITE) {
            /* ring 1/2: intern writes quarantine and drafts. main/ and tests/rom/ are ring 0. */
            if (!prefix(in->path, "hold/") && !prefix(in->path, "proposed/"))
                FAULT("ring: intern writes hold/ or proposed/ only, not %.160s", in->path);
            if (copy_field(in->rest, sizeof in->rest, trim(p))) FAULT("payload too long");
        }
        return 1;
    case OP_EXEC:
        if (!a) FAULT("EXEC needs <program>");
        if (copy_field(in->slot, sizeof in->slot, a)) FAULT("field too long");
        if (!safe_rel(a) || !prefix(a, "tools/") || !suffix(a, ".py")) FAULT("EXEC runs tools/*.py only, not %.160s", a);
        if (copy_field(in->rest, sizeof in->rest, trim(p))) FAULT("args too long");
        {
            char tmp[256], *q = tmp, *t;
            memcpy(tmp, in->rest, sizeof tmp);
            while ((t = tok(&q)) != NULL) if (!safe_rel(t)) FAULT("arg escapes the world: %.160s", t);
        }
        return 1;
    case OP_TEST:
        b = tok(&p);
        {
            int k = -1;
            for (int i = 0; a && i < 4; i++) if (!strcasecmp(a, KIND_NAME[i])) k = i;
            if (k < 0) FAULT("TEST without kind (PURE SCALAR JUDGE VISUAL)");
            if (!b) FAULT("TEST needs <kind> <path>");
            snprintf(in->slot, sizeof in->slot, "%s", KIND_NAME[k]);
        }
        if (copy_field(in->path, sizeof in->path, b)) FAULT("field too long");
        if (!safe_rel(b) || !prefix(b, "tests/rom/") || !suffix(b, ".py")) FAULT("TEST runs tests/rom/*.py only, not %.160s", b);
        if (*trim(p)) FAULT("TEST takes <kind> <path> only");
        return 1;
    case OP_WAIT: {
        if (!a) FAULT("WAIT needs <ms>");
        char *end;
        errno = 0;
        unsigned long ms = strtoul(a, &end, 10);
        if (errno || *end || a[0] == '-' || ms > 3600000ul) FAULT("WAIT <ms> not a number: %.160s", a);
        if (*trim(p)) FAULT("WAIT takes <ms> only");
        in->ms = (uint32_t)ms;
        return 1;
    }
    }
    FAULT("unreachable");
}

/* ---- the five actuators, as tools behind the frame ---- */

static int wired(Session *s, int slot, const char *name) {
    if (slot < 0) return ev(s, 1, "deny slot=%s unknown", name);
    if (!plugged(&s->bus, slot)) return ev(s, 1, "deny slot=%s unplugged", name);
    return 0;
}

static int t_read(Session *s, void *arg) {
    Instr *in = arg;
    int sl = slot_of(in->slot);
    if (wired(s, sl, in->slot)) return 1;
    if (sl != SLOT_FS) return ev(s, 1, "deny slot=%s no device in foundation", in->slot);
    char p[1024], buf[4097];
    if (path_join(p, sizeof p, s->root, in->path)) return ev(s, 1, "path too long");
    FILE *f = fopen(p, "rb");
    if (!f) return ev(s, 1, "op=read slot=fs path=%s err=%s", in->path, strerror(errno));
    size_t cap = s->bus.cap[SLOT_FS], n = fread(buf, 1, cap + 1 < sizeof buf ? cap + 1 : sizeof buf, f);
    fclose(f);
    if (n > cap) return ev(s, 1, "leash op=read path=%s bytes>%zu", in->path, cap);
    dprintf(g_log, "READ fs %s %zu bytes\n", in->path, n);
    if (n && write(g_log, buf, n) < 0) { /* log is best-effort */ }
    return ev(s, 0, "op=read kind=none slot=fs path=%s bytes=%zu dirty=0", in->path, n);
}

static int t_write(Session *s, void *arg) {
    Instr *in = arg;
    int sl = slot_of(in->slot);
    if (wired(s, sl, in->slot)) return 1;
    if (sl != SLOT_FS) return ev(s, 1, "deny slot=%s no device in foundation", in->slot);
    char p[1024], text[300];
    snprintf(text, sizeof text, "%s%s", in->rest, in->rest[0] ? "\n" : "");
    size_t n = strlen(text);
    if (n > s->bus.cap[SLOT_FS]) return ev(s, 1, "leash op=write bytes>%u", s->bus.cap[SLOT_FS]);
    if (path_join(p, sizeof p, s->root, in->path)) return ev(s, 1, "path too long");
    char *slash = strrchr(p, '/');
    *slash = 0;
    int bad = mkdirs(p);
    *slash = '/';
    if (bad || write_atomic(p, text)) return ev(s, 1, "op=write path=%s err=%s", in->path, strerror(errno));
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
        if (c >= MAX_ARGV + 2) return ev(s, 1, "op=exec too many args");
        argv[c++] = t;
    }
    argv[c] = NULL;
    uint64_t nb = 0;
    dprintf(g_log, "EXEC %s %s\n", in->slot, in->rest);
    int rc = child_run(s->root, argv, JAIL_FULL, NULL, 0, &nb, s->t_tool_ms, g_log, g_log);
    if (rc == -2) return ev(s, 1, "knife op=exec prog=%s timeout>%ums", in->slot, s->t_tool_ms);
    if (rc == -3) return ev(s, 1, "halt op=exec prog=%s child killed", in->slot);
    if (nb > s->bus.cap[SLOT_TTY]) return ev(s, 1, "leash op=exec out=%llu>%u", (unsigned long long)nb, s->bus.cap[SLOT_TTY]);
    return ev(s, rc != 0, "op=exec kind=none slot=%s rc=%d out=%llu dirty=0", in->slot, rc, (unsigned long long)nb);
}

static int t_test(Session *s, void *arg) {
    Instr *in = arg;
    if (!strcmp(in->slot, "JUDGE")) {
        /* dirty DMA needs the judge card and the radio. radio is off. */
        if (!plugged(&s->bus, SLOT_JUDGE) || !plugged(&s->bus, SLOT_RADIO))
            return ev(s, 1, "deny op=test kind=judge judge/radio unplugged");
        return ev(s, 1, "deny op=test kind=judge no judge device in foundation");
    }
    if (!strcmp(in->slot, "VISUAL")) {
        if (!plugged(&s->bus, SLOT_FB)) return ev(s, 1, "deny op=test kind=visual fb unplugged");
        return ev(s, 1, "deny op=test kind=visual no fb device in foundation");
    }
    char *argv[] = {"python3", "tools/test_runner.py", "--kind", in->slot, in->path, NULL};
    char out[256] = "";
    dprintf(g_log, "TEST %s %s\n", in->slot, in->path);
    int rc = child_run(s->root, argv, JAIL_NET_ONLY, out, sizeof out, NULL, s->t_tool_ms, g_log, g_log);
    out[strcspn(out, "\r\n")] = 0;
    if (rc == -2) return ev(s, 1, "knife op=test path=%s timeout>%ums", in->path, s->t_tool_ms);
    if (rc == -3) return ev(s, 1, "halt op=test path=%s child killed", in->path);
    return ev(s, rc != 0, "op=test kind=%s slot=fs path=%s rc=%d result=\"%s\" dirty=0",
              !strcmp(in->slot, "PURE") ? "pure" : "scalar", in->path, rc, out);
}

static int t_wait(Session *s, void *arg) {
    Instr *in = arg;
    if (in->ms > s->t_tool_ms) return ev(s, 1, "op=wait ms=%u > T_tool=%u", in->ms, s->t_tool_ms);
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

static int armed(void) { return owner_token_present(g_root, getenv("BENCH_TOKEN")); }

static Mailbox g_mb = {-1, -1, -1};

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

static void fmt_instr(const Instr *in, char *out, size_t n) {
    switch (in->op) {
    case OP_WAIT: snprintf(out, n, "WAIT %u\n", in->ms); break;
    case OP_EXEC: snprintf(out, n, "EXEC %s%s%s\n", in->slot, in->rest[0] ? " " : "", in->rest); break;
    default:
        snprintf(out, n, "%s %s %s%s%s\n", OP_NAME[in->op], in->slot, in->path,
                 in->rest[0] ? " " : "", in->rest);
    }
}

/* the frame's gate. KILL first (the owner's hand), then the owner's token. */
static int run_gate(Session *s) {
    if (g_halt || exists(s->dir, "KILL")) return ev(s, 3, "halt=kill");
    if (!armed()) return ev(s, 5, "halt=disarmed owner token gone");
    char n[16], why[128];
    snprintf(n, sizeof n, "%u", s->n + 1);
    int ok = mb_ask(&g_mb, "FRAME_OK", n, why, sizeof why);
    if (ok < 0) return ev(s, 6, "halt=helper-lost no FRAME_OK answer");
    if (ok == 0) return ev(s, 5, "halt=disarmed helper: %.100s", why);
    return 0;
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
    if (!armed()) {
        fprintf(stderr, "run: not armed — no owner token. set BENCH_TOKEN to a token file, "
                        "or create %s under the world root. no frames ran.\n", TOKEN_REL);
        return 5;
    }
    unsigned long n = N_MAX_DEFAULT;
    const char *script = NULL;
    /* hold quota: --hold-quota beats BENCH_HOLD_QUOTA beats the built-in default. */
    const char *hq_src = getenv("BENCH_HOLD_QUOTA");
    if (hq_src && !*hq_src) hq_src = NULL;
    for (int i = 0; i < argc; i++) {
        if (!strcmp(argv[i], "--n") && i + 1 < argc) {
            char *end;
            n = strtoul(argv[++i], &end, 10);
            if (*end) n = 0;
        } else if (!strcmp(argv[i], "--hold-quota") && i + 1 < argc) {
            hq_src = argv[++i];
        } else if (!script) {
            script = argv[i];
        } else {
            fprintf(stderr, "usage: bench run [--n N] [--hold-quota BYTES] [script|-]\n");
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

    FILE *f = (script && strcmp(script, "-")) ? fopen(script, "r") : stdin;
    if (!f) { fprintf(stderr, "run: cannot open %s: %s\n", script, strerror(errno)); return 2; }
    static Instr prog[MAX_OPS];
    int nops = 0, ln = 0;
    char line[LINE_BYTES], err[256];
    while (fgets(line, sizeof line, f)) {
        ln++;
        if (!strchr(line, '\n') && !feof(f)) { fprintf(stderr, "FAULT line %d: line too long\n", ln); return 1; }
        int r = parse_line(line, ln, &prog[nops < MAX_OPS ? nops : MAX_OPS - 1], err, sizeof err);
        if (r < 0) { fprintf(stderr, "FAULT line %d: %s\n", ln, err); return 1; }
        if (r == 1 && ++nops > MAX_OPS) { fprintf(stderr, "FAULT line %d: script over %d ops\n", ln, MAX_OPS); return 1; }
    }
    if (f != stdin) fclose(f);

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
    if (session_start(&s, g_root, dir, (uint32_t)n, (uint32_t)n, 0, 0, 0, hold_quota)) {
        fprintf(stderr, "FAULT session start: snap s0 failed\n");
        return 1;
    }
    s.gate = run_gate;

    int rc = 0;
    for (int i = 0; i < nops; i++) {
        if (s.n >= s.n_max) {
            /* the edge, before the work: N is a budget, not a suggestion */
            ev(&s, 1, "fault=over-N n=%u N=%u", s.n, s.n_max);
            s.bus.lamps = lamp_set(s.bus.lamps, LAMP_HOLD);
            snap(&s, "fault");
            session_state(&s, "fault");
            fprintf(stderr, "FAULT line %d: over N (%u)\n", prog[i].line, s.n_max);
            rc = 1;
            break;
        }
        s.ev[0] = 0;
        int k_due = ((s.n + 1) % s.k_snap) == 0;
        int fr = frame(&s, prog[i].op, TOOL[prog[i].op], &prog[i], k_due);
        if (fr > 0) {
            /* stopped at the gate: this op never ran and has no snap */
            session_state(&s, fr == 3 ? "halt" : fr == 5 ? "disarmed" : "fault");   /* 6: helper lost */
            fprintf(stderr, "HALT line %d: %s\n", prog[i].line, s.ev);
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
        if (fr != 0) {
            session_state(&s, "fault");
            fprintf(stderr, "FAULT line %d: %s\n", prog[i].line, s.ev);
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
    if (current_dir(dir, sizeof dir, id, sizeof id)) { fprintf(stderr, "kill: no session\n"); return 1; }
    if (path_join(path, sizeof path, dir, "KILL") || write_atomic(path, "KILL\n")) return 1;
    if (path_join(path, sizeof path, dir, "PID") == 0 && read_small(path, buf, sizeof buf) == 0) {
        pid_t pid = (pid_t)atoi(buf);
        if (pid > 0 && kill(pid, 0) == 0) kill(pid, SIGTERM);
    }
    sn[0] = 0;
    if (path_join(path, sizeof path, dir, "STATE") == 0 && read_small(path, buf, sizeof buf) == 0)
        kv(buf, "snap", sn, sizeof sn);
    printf("KILL %s last snap %s\n", id, sn[0] ? sn : "-");
    return 0;
}

static int cmd_demo(void) {
    if (rom_ok() != 0) return 4;
    char *argv[] = {"python3", "tools/test_runner.py", NULL};
    char out[256] = "";
    int rc = child_run(g_root, argv, JAIL_NET_ONLY, out, sizeof out, NULL, 300000, -1, -1);
    char *nl = strchr(out, '\n');
    if (nl) *nl = 0;
    if (rc != 0) {
        printf("%s\n", prefix(out, "RED") ? out : "RED");
        return 1;
    }
    printf("%s\n", prefix(out, "GREEN") ? out : "RED");
    return prefix(out, "GREEN") ? 0 : 1;
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

int main(int argc, char **argv) {
    const char *r = getenv("BENCH_ROOT");
    if (r && *r) g_root = r;
    if (argc < 2) goto usage;
    if (!strcmp(argv[1], "status")) return cmd_status();
    if (!strcmp(argv[1], "run")) return cmd_run(argc - 2, argv + 2);
    if (!strcmp(argv[1], "kill")) return cmd_kill();
    if (!strcmp(argv[1], "demo")) return cmd_demo();
    if (!strcmp(argv[1], "snap-ls")) return cmd_snap_ls();
usage:
    fprintf(stderr, "usage: bench status | run [--n N] [--hold-quota BYTES] [script|-] | kill | demo | snap-ls\n");
    return 2;
}
