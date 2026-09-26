/* frame.h — the edges of one step. one thread owns this. */
#ifndef FRAME_H
#define FRAME_H
#include <stddef.h>
#include <stdint.h>
#include "woz_bus.h"

#ifndef N_MAX_DEFAULT
#define N_MAX_DEFAULT 8
#endif

/* same numbering as isa/hotz_isa.py Op. five. there is no sixth. */
typedef enum { OP_READ=1, OP_WRITE, OP_EXEC, OP_TEST, OP_WAIT } Op;

typedef struct {
    uint32_t n_max, k_snap, n;
    uint32_t t_step_ms, t_sess_ms;
    uint64_t t0_ns, last_snap_ns;
    Bus      bus;            /* woz bits — lamps live here, we do not keep a second copy */
    uint32_t k;              /* next snap index: snap-<k>/ */
    char     snap_id[24];
    char     ev[256];        /* evidence ticket of the current step; lands in the next MANIFEST */
    char     root[512];      /* the world: main/ hold/ tools/ tests/rom/ */
    char     dir[768];       /* sessions/<id> */
} Session;

typedef int (*Tool)(Session *s, void *arg);

uint64_t nowns(void);
int  session_start(Session *s, const char *root, const char *dir,
                   uint32_t n, uint32_t k, uint32_t ts, uint32_t tS);
int  frame(Session *s, Op op, Tool tool, void *arg, int k_due);
int  snap(Session *s, const char *why);
int  session_state(const Session *s, const char *status);

/* tools are children with a knife. returns exit code, -2 on timeout, -1 on spawn failure.
   stdout is captured into out (truncated) and counted in *nbytes; copied to log_fd if >= 0.
   err_fd >= 0 receives the child's stderr, otherwise it is inherited. */
int  child_run(const char *root, char *const argv[], char *out, size_t outsz,
               uint64_t *nbytes, uint32_t timeout_ms, int log_fd, int err_fd);

int  mkdirs(const char *path);
int  write_atomic(const char *path, const char *text);
int  path_join(char *out, size_t n, const char *a, const char *b);

#endif
