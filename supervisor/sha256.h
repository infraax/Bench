/* sha256.h — one hash, no library. public domain.
 * a snapshot without a hash is a rumor. this is the C path so the frame does not
 * pay a python interpreter boot to photograph the board. */
#ifndef SHA256_H
#define SHA256_H
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t state[8];
    uint64_t nbits;
    uint8_t  buf[64];
    size_t   len;
} Sha256;

void sha256_init(Sha256 *c);
void sha256_update(Sha256 *c, const void *data, size_t n);
void sha256_final(Sha256 *c, char hex[65]);   /* writes 64 hex chars + NUL */

/* tree hash over paths under root, matching tools/hash.py byte for byte:
 *   for each path arg, in order:
 *     missing        -> "missing\0" <path> "\0"
 *     regular file   -> <relpath> "\0" <len> "\0" <bytes>
 *     directory      -> same, for every regular non-symlink file, sorted by relpath
 * returns 0 on success and writes hex[65]; -1 on error. */
int tree_hash(const char *root, const char *const *paths, int npaths, char hex[65]);

#endif
