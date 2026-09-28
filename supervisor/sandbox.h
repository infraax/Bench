/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* sandbox.h — conservation of authority.
 *
 * a child of the supervisor gets fewer rights than the supervisor, dropped in the
 * child between fork() and execvp(). intelligence is not a syscall: a smarter tool
 * does not get the antenna back by being clever, because the antenna syscalls fault.
 *
 * honest limits (Karpathy/Woz): this is not a thermodynamic seal.
 *   - execve stays ALLOWED: the filter is installed before we exec python, so we cannot
 *     ban the one exec that starts the tool. banning tool-spawned sub-execs needs a
 *     sealed non-python tool (spec Law 2), which foundation does not ship.
 *   - default-deny seccomp on a full CPython is too fragile to be honest here; we KILL a
 *     named set of ambient-authority syscalls (network, ptrace, namespaces, mount, keys, io_uring)
 *     instead. that removes the radio in the kernel, not just by not-compiling it.
 *   - namespaces: every tool child gets a private mount namespace (plus a user namespace when
 *     not root) showing only the world, /usr and a private /tmp; main/, ROM and sessions/ are
 *     read-only in it. it cannot be set up -> the child does not run.
 * The real leash stays structural: the intern speaks only five opcodes into the C parser
 * and never holds this interpreter itself. */
#ifndef SANDBOX_H
#define SANDBOX_H

typedef enum {
    JAIL_NET_ONLY = 0,   /* seccomp net/ptrace/ns deny. for Ring-0 muscle (TEST): needs /tmp. */
    JAIL_FULL     = 1,    /* + landlock write-jail to hold/ and proposed/. for EXEC (intern). */
} Jail;

/* build a scrubbed environment for a tool child (no LD_PRELOAD, no PYTHONPATH, fixed PATH,
   PYTHONDONTWRITEBYTECODE so a landlocked child does not try to write __pycache__).
   returns a NULL-terminated, malloc'd envp the caller passes to child_run; NULL on OOM. */
char **tool_env(void);

/* drop authority in THIS (child) process. must be called after fork, before exec,
   with cwd already at the world root. returns 0 on success; on any failure the child
   must _exit() (fail closed) rather than run unsandboxed. */
int sandbox_apply(Jail jail);

/* the namespace step of sandbox_apply alone (sandbox.c): the child's view becomes the world
   (cwd), /usr, /dev/null and a private /tmp. exposed for tests/perf/ns_cost.c. */
int sandbox_world_only(void);

#endif
