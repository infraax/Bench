/* refusal.c — the one table of rule id -> fix. mirrored in tests/rom/test_refusals.py.
 * ids are stable: renaming one is a ROM change. a fix says what to do instead, in one line. */
#define _POSIX_C_SOURCE 200809L
#include <string.h>
#include "refusal.h"

const Rule RULES[] = {
    /* parse: the line dies at birth, before any frame */
    {"line-long",     "keep each line under 512 bytes"},
    {"script-long",   "split the script: at most 64 ops per run"},
    {"verb-super",    "that word is the owner's; use one of READ WRITE EXEC TEST WAIT"},
    {"verb-unknown",  "use one of the five verbs: READ WRITE EXEC TEST WAIT"},
    {"shape-rw",      "write READ fs <path> or WRITE fs <path> <one line>"},
    {"field-long",    "shorten it: slot under 128 bytes, path and payload under 256"},
    {"path-escape",   "use a relative path inside the world: no leading / and no .."},
    {"read-payload",  "READ takes <slot> <path> only; drop the words after the path"},
    {"write-ring",    "write under hold/ or proposed/; main/ is Ring 0"},
    {"exec-shape",    "write EXEC tools/<name>.py <args>"},
    {"exec-prog",     "EXEC runs tools/*.py only; copy a draft to proposed/ and ask the owner to crown it"},
    {"exec-arg",      "each EXEC arg is a relative path or word inside the world: no leading / and no .."},
    {"exec-argc",     "pass at most 16 args; name a file holding the rest"},
    {"test-kind",     "write TEST PURE <tests/rom/test_x.py> (kinds: PURE SCALAR)"},
    {"test-shape",    "write TEST <kind> <tests/rom/test_x.py> and nothing after it"},
    {"test-path",     "TEST runs crowned tests/rom/*.py only; draft under tests/proposed/ for the owner"},
    {"wait-shape",    "write WAIT <ms>, a whole number of milliseconds up to T_tool"},
    /* run: the op was framed and refused, snapped with rule= in its evidence */
    {"slot-unknown",  "use slot fs (slots: fs tty fb judge radio)"},
    {"slot-pulled",   "that slot is pulled in foundation; use fs"},
    {"judge-pulled",  "JUDGE needs the judge card and radio, both pulled; use TEST PURE or SCALAR"},
    {"visual-pulled", "VISUAL needs the fb card, pulled; use TEST PURE or SCALAR"},
    {"fs-path",       "name an existing regular file; no component may be a symlink"},
    {"fs-cap",        "keep a READ or WRITE within the fs cap (4096 bytes); split the file"},
    {"tty-cap",       "print at most 4096 bytes; bound the tool's output"},
    {"worker-setup",  "the worker could not start (jail, chdir or exec); the owner checks the kernel and the world"},
    {"sandbox",       "the tool made a forbidden syscall (network, ptrace, namespaces, mount, keys, io_uring); drop it"},
    {"out-ceil",      "the tool printed past 1 MiB and was killed; bound its output"},
    {"t-tool",        "finish within T_tool (5000 ms); split the work across steps"},
    {"hold-bytes",    "hold/ grew past its byte quota this session; write less or ask the owner for --hold-quota"},
    {"hold-files",    "hold/ grew past its entry quota this session; write fewer files or ask for --hold-files"},
    {"test-moved",    "a TEST may change only hold/, proposed/ and /tmp; the owner must re-arm"},
    {"t-frame",       "the step's own bookkeeping ran past T_frame; write fewer new files per step"},
    {"t-session",     "the session ran past T_session; use fewer or shorter steps"},
    {"over-n",        "the run is over N steps; ask the owner for --n or split the script"},
    {"internal",      "not the intern's to fix; the owner reads sessions/<id>/log"},
    /* gate: the op never ran, no snap */
    {"kill",          "the owner stopped the run; nothing to fix from the intern side"},
    {"disarmed",      "the owner's token is gone or changed; only the owner can re-arm"},
    {"helper-lost",   "bench-helper stopped answering; the owner restarts the run"},
};

const unsigned RULES_N = sizeof RULES / sizeof *RULES;

const char *rule_fix(const char *id) {
    for (unsigned i = 0; i < RULES_N; i++) if (!strcmp(RULES[i].id, id)) return RULES[i].fix;
    return NULL;
}

void rule_say(FILE *f, const char *text) {
    const char *p = text ? strstr(text, "rule=") : NULL;
    if (!p) return;
    char id[32];
    size_t l = strcspn(p + 5, " \t\n");
    if (l >= sizeof id) return;
    memcpy(id, p + 5, l);
    id[l] = 0;
    const char *fix = rule_fix(id);
    fprintf(f, "  rule=%s fix: %s\n", id, fix ? fix : "(no rule in the table — a bench bug)");
}
