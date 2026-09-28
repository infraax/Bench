/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* mailbox.h — bench's side of the helper mailbox. see helper.c for the three words. */
#ifndef MAILBOX_H
#define MAILBOX_H
#include <stddef.h>
#include <sys/types.h>

/* the one helper bench talks to. a helper answering PING with anything else is refused. */
#define HELPER_VERSION "helper v0"

typedef struct {
    int   fd;      /* connected to the helper; CLOEXEC, so no tool child inherits it */
    pid_t pid;     /* the helper */
    int   log_fd;  /* every exchange is a log line; -1 = no log */
} Mailbox;

/* start bench-helper (next to this binary) on a socket at <dir>/helper.sock, then PING it.
   the path is unlinked once paired. 0 ok; -1 with why filled = fail closed. */
int  mb_open(Mailbox *m, const char *dir, const char *root, int log_fd, char *why, size_t whyn);

/* ask one word (arg may be NULL). 1 yes, 0 no, -1 broken or silent. reply gets the reason. */
int  mb_ask(Mailbox *m, const char *word, const char *arg, char *reply, size_t n);

/* close the line; the helper sees EOF and exits. reaped here. */
void mb_close(Mailbox *m);

#endif
