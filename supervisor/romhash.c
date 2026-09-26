/* romhash.c — build tool. prints the tree hash of tests/rom for the given root
 * (default "."). the Makefile bakes this into supervisor/rom_hash.h, and the
 * supervisor recomputes it at boot with the same tree_hash. change a rom file,
 * rebuild, or the binary refuses to boot on the old crown.
 *
 * this pins the ROM *content*. it cannot pin the binary into itself (a hash cannot
 * contain its own hash); binary integrity is a job for the packager, not foundation. */
#include <stdio.h>
#include "sha256.h"

int main(int argc, char **argv) {
    const char *root = argc > 1 ? argv[1] : ".";
    const char *paths[] = {"tests/rom"};
    char hex[65];
    if (tree_hash(root, paths, 1, hex) != 0) {
        fprintf(stderr, "romhash: cannot hash %s/tests/rom\n", root);
        return 1;
    }
    printf("%s\n", hex);
    return 0;
}
