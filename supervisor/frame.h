/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* frame.h — the edges of one step. one thread owns this. */
#ifndef FRAME_H
#define FRAME_H
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include "woz_bus.h"
#include "sandbox.h"
#include "arm.h"

#ifndef N_MAX_DEFAULT
#define N_MAX_DEFAULT 8
#endif

/* hold/ budget per session: bytes hold/ may grow past its size at s0. counted after every
   tool (WRITE and anything an EXEC'd tool wrote). over quota is a failed step, snapped.
   this is the default; the owner may set it per run (--hold-quota, BENCH_HOLD_QUOTA). */
#ifndef HOLD_QUOTA_BYTES
#define HOLD_QUOTA_BYTES 65536u
#endif
#define HOLD_QUOTA_CEIL  0xffffffffull   /* a run-time override above this is a usage error */

/* and how many entries (regular files + directories) hold/ may grow by. bytes alone let a
   tool make 65 536 one-byte files, and every snap would copy them all. same override pattern:
   --hold-files, BENCH_HOLD_FILES. */
#ifndef HOLD_QUOTA_FILES
#define HOLD_QUOTA_FILES 256u
#endif

/* same numbering as isa/hotz_isa.py Op. five. there is no sixth. */
typedef enum { OP_READ=1, OP_WRITE, OP_EXEC, OP_TEST, OP_WAIT } Op;

typedef struct Session Session;

/* the frame's gate: asked before every step. 0 = go. >0 = stop here, no step, no snap;
   the value is the run's exit code. sets s->ev to the reason. */
typedef int (*Gate)(Session *s);

struct Session {
    uint32_t n_max, k_snap, n;
    uint32_t t_step_ms;   /* T_frame: the C thread's own work per step (snap). small. */
    uint32_t t_tool_ms;   /* T_tool:  a child's wall clock. python boot lives here, not in the frame. */
    uint32_t t_sess_ms;
    uint64_t t0_ns, last_snap_ns;
    uint64_t hold_base;      /* bytes in hold/ at session start; the quota counts growth past it */
    uint64_t hold_quota;     /* frozen at start, like N */
    uint64_t hold_base_files;   /* entries in hold/ at session start */
    uint64_t hold_files_quota;  /* frozen at start */
    Gate     gate;           /* KILL, owner token, helper: checked inside frame(), not beside it */
    TokenId  tok;            /* the token that armed this run, pinned; any change disarms */
    int      tainted;        /* a TEST step broke its post-conditions: the run ends disarmed */
    Bus      bus;            /* woz bits — lamps live here, we do not keep a second copy */
    uint32_t k;              /* next snap index: snap-<k>/ */
    int      prev_board;     /* index of the last snap that holds a board (-1: none) — delta source */
    uint64_t frame_us;       /* the last frame's C-thread time (gate + checks + snap), for the log */
    uint64_t tool_us;        /* the last frame's tool wall time */
    char     snap_id[24];
    char     ev[256];        /* evidence ticket of the current step; lands in the next MANIFEST */
    char     out[128];       /* the step's out-<n> file: name, bytes, sha256. MANIFEST out= */
    char     root[512];      /* the world: main/ hold/ tools/ tests/rom/ */
    char     dir[768];       /* sessions/<id> */
};

typedef int (*Tool)(Session *s, void *arg);

/* set by the signal handler; child_run and WAIT watch it. one flag, one owner (frame.c). */
extern volatile sig_atomic_t g_halt;

/* no worker outlives its frame. bench is a child subreaper (main.c), so a worker's descendants
   reparent to bench even after setsid(); child_run SIGKILLs and reaps every child of bench but
   g_keep_pid (the helper) once the worker returns. g_strays: how many it killed for the last
   worker (the step's evidence says strays=N when N > 0). */
extern pid_t g_keep_pid;
extern unsigned g_strays;

uint64_t nowns(void);
#define T_TOOL_DEFAULT_MS 5000u   /* a child's wall clock unless a session says otherwise */
void bus_foundation(Bus *b);   /* foundation plugs and caps: fs, tty wired; fb, judge, radio pulled */
int  session_start(Session *s, const char *root, const char *dir,
                   uint32_t n, uint32_t k, uint32_t ts, uint32_t tt, uint32_t tS,
                   uint64_t hq, uint64_t hf);
int  frame(Session *s, Op op, Tool tool, void *arg, int k_due);   /* 0 ok, >0 gate stop, -1 fault */
int  snap(Session *s, const char *why);
int  session_state(const Session *s, const char *status);

/* the hard ceiling on a tool child's output to disk. the tty cap is an evidence leash checked
   after the fact; this is the wall: a child past it is killed mid-stream so a flood cannot fill
   the disk within T_tool. generous, so real output (a failing test's traceback) survives. */
#ifndef OUT_CEIL_BYTES
#define OUT_CEIL_BYTES (1u<<20)
#endif

/* tools are children with a knife. returns exit code, -2 on timeout, -3 on halt (g_halt: the
   child is killed now, not after T_tool), -4 on output past out_max (killed), -5 killed by the seccomp filter (SIGSYS),
   -6 the worker never started (chdir, jail or exec failed before the tool ran),
   -1 on spawn failure or another signal.
   out_max = 0 means no ceiling.
   stdout is captured into out (truncated) and counted in *nbytes; copied to log_fd if >= 0.
   err_fd >= 0 receives the child's stderr, otherwise it is inherited. */
int  child_run(const char *root, char *const argv[], Jail jail, char *out, size_t outsz,
               uint64_t *nbytes, uint32_t timeout_ms, uint64_t out_max, int log_fd, int err_fd);

/* bytes in regular files, and entries (regular files + dirs), under path — the top itself
   not counted. links and devices are not board state, same as snap. adds into the outputs. */
int  tree_count(const char *path, uint64_t *bytes, uint64_t *entries);

/* a plain full copy of a board tree (regular files and dirs), no links. restore uses it:
   hold/ is writable by tools, so it must never share an inode with a snap. */
int  copy_board(const char *src, const char *dst);

int  mkdirs(const char *path);
int  write_atomic(const char *path, const char *text);
int  path_join(char *out, size_t n, const char *a, const char *b);

#endif
