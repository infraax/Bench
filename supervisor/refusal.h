/* refusal.h — every refusal bench emits has a stable rule id and a one-line fix.
 *
 * the id travels as evidence (`rule=<id>`, key=value, in the MANIFEST); the fix is printed
 * beside the fault so the intern can act on it. the table is mirrored in ROM
 * (tests/rom/test_refusals.py) and `bench rules` prints it for the harness to compare.
 */
#ifndef BENCH_REFUSAL_H
#define BENCH_REFUSAL_H

#include <stdio.h>

typedef struct { const char *id, *fix; } Rule;

extern const Rule RULES[];
extern const unsigned RULES_N;

/* the fix for <id>, or NULL if the id is not in the table. */
const char *rule_fix(const char *id);

/* print "  rule=<id> fix: <fix>\n" for the first rule=<id> in text; nothing if none. */
void rule_say(FILE *f, const char *text);

#endif
