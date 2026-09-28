#!/bin/sh
# SPDX-License-Identifier: MIT OR Apache-2.0
# agent-setup.sh — the machine card every agent session starts from. `make env` runs it.
#
# deterministic, offline, installs nothing. prints the card and writes it to
# ledger/<stamp>-<sha>/ENV.txt, with ledger/latest pointing at that dir.
# a missing prerequisite: prints the exact install line and exits 2.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

missing=""
need() { command -v "$1" >/dev/null 2>&1 || missing="$missing $1"; }
need cc; need make; need python3; need git
if [ -n "$missing" ]; then
    echo "agent-setup: missing:$missing" >&2
    echo "  Debian/Ubuntu: sudo apt-get install -y build-essential python3 git" >&2
    echo "  (or: sh scripts/bootstrap-debian.sh)" >&2
    exit 2
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "agent-setup: python3 >= 3.10 required, found $(python3 --version 2>&1)" >&2
    echo "  Debian/Ubuntu: sudo apt-get install -y python3" >&2
    exit 2
fi

sha=$(git rev-parse --short HEAD 2>/dev/null || echo nogit)
stamp=$(date -u +%Y%m%d-%H%M%S)
dir="ledger/$stamp-$sha"
n=1
while [ -e "$dir" ]; do dir="ledger/$stamp-$sha.$n"; n=$((n + 1)); done
mkdir -p "$dir"

os=$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || echo unknown)
{
    echo "stamp=$stamp"
    echo "git_sha=$sha"
    echo "git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo -)"
    echo "git_dirty=$(git status --porcelain 2>/dev/null | grep -qv '^??' && echo yes || echo no)"
    echo "uname=$(uname -a)"
    echo "os=$os"
    echo "nproc=$(nproc 2>/dev/null || echo ?)"
    echo "uid=$(id -u)"
    echo "cc=$(cc -dumpversion 2>/dev/null || echo ?)"
    echo "make=$(make --version 2>/dev/null | head -1)"
    echo "python=$(python3 --version 2>&1)"
    echo "pytest=$(python3 -c 'import pytest; print(pytest.__version__)' 2>/dev/null || echo none)"
    echo "lsm=$(cat /sys/kernel/security/lsm 2>/dev/null || echo unreadable)"
    echo "bench_built=$([ -x supervisor/bench ] && echo yes || echo no)"
    echo "helper_built=$([ -x supervisor/bench-helper ] && echo yes || echo no)"
} > "$dir/ENV.txt"

ln -sfn "$(basename "$dir")" ledger/latest
cat "$dir/ENV.txt"
echo "ledger: $dir/ENV.txt"
