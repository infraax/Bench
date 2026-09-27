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
    Gate     gate;           /* KILL, owner token, helper: checked inside frame(), not beside it */
    TokenId  tok;            /* the token that armed this run, pinned; any change disarms */
    int      tainted;        /* a TEST step broke its post-conditions: the run ends disarmed */
    Bus      bus;            /* woz bits — lamps live here, we do not keep a second copy */
    uint32_t k;              /* next snap index: snap-<k>/ */
    char     snap_id[24];
    char     ev[256];        /* evidence ticket of the current step; lands in the next MANIFEST */
    char     root[512];      /* the world: main/ hold/ tools/ tests/rom/ */
    char     dir[768];       /* sessions/<id> */
};

typedef int (*Tool)(Session *s, void *arg);

/* set by the signal handler; child_run and WAIT watch it. one flag, one owner (frame.c). */
extern volatile sig_atomic_t g_halt;

uint64_t nowns(void);
int  session_start(Session *s, const char *root, const char *dir,
                   uint32_t n, uint32_t k, uint32_t ts, uint32_t tt, uint32_t tS, uint64_t hq);
int  frame(Session *s, Op op, Tool tool, void *arg, int k_due);   /* 0 ok, >0 gate stop, -1 fault */
int  snap(Session *s, const char *why);
int  session_state(const Session *s, const char *status);

/* tools are children with a knife. returns exit code, -2 on timeout, -3 on halt (g_halt: the
   child is killed now, not after T_tool), -1 on spawn failure.
   stdout is captured into out (truncated) and counted in *nbytes; copied to log_fd if >= 0.
   err_fd >= 0 receives the child's stderr, otherwise it is inherited. */
int  child_run(const char *root, char *const argv[], Jail jail, char *out, size_t outsz,
               uint64_t *nbytes, uint32_t timeout_ms, int log_fd, int err_fd);

/* bytes in regular files under path (links and devices are not counted, same as snap). */
int  tree_bytes(const char *path, uint64_t *out);

int  mkdirs(const char *path);
int  write_atomic(const char *path, const char *text);
int  path_join(char *out, size_t n, const char *a, const char *b);

#endif
