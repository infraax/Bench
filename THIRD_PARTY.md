# Third-party material

What in this tree was not written for Bench, and what Bench depends on without shipping it.

## In tree

| File | Origin | Terms |
|---|---|---|
| `supervisor/sha256.c` (SHA-256 core: constants, compression, padding) | written for this tree from the FIPS 180-4 specification; no code copied | marked public domain in its header; the tree-hash functions in the same file are project code under `MIT OR Apache-2.0` |

## SPDX lines

Every original `.c`, `.h` and `.py` carries `SPDX-License-Identifier: MIT OR Apache-2.0` except
`supervisor/sandbox.c` (frozen this session; covered by the project license all the same) and the
generated `supervisor/rom_hash.h`.

## Vendored

| Name | Version | License | Path |
|---|---|---|---|
| — | — | — | — |

None. Bench does not vendor other harnesses or libraries. The site (`docs/`) ships no third-party
JavaScript, CSS or fonts: `docs/assets/js/site.js` and `docs/assets/css/crypt.css` are project
code. The diagrams in `docs/assets/diagrams/*.svg` are project drawings rendered once with
[mermaid-cli](https://github.com/mermaid-js/mermaid-cli) 11 (MIT), a development tool that is
not shipped; their Mermaid sources are in `docs/assets/diagrams/src/`. `docs/research/` stores only URLs, commit
SHAs and line counts of the audited repos; `docs/research/fetch.sh` re-fetches them into a gitignored
directory on demand.

## Runtime, not shipped

| Component | Used for | Shipped? |
|---|---|---|
| Linux kernel (≥ 5.13: landlock, seccomp, namespaces) | worker isolation | no |
| glibc / a C11 compiler | building and running `supervisor/` | no |
| CPython 3.10+ (stdlib only) | `isa/`, `tools/`, tests | no |
