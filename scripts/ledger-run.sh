#!/bin/sh
# SPDX-License-Identifier: MIT OR Apache-2.0
# ledger-run.sh <command...> — run a command into the ledger; print only the summary.
#
# ledger/<stamp>-<sha>/
#   ENV.txt          copied from ledger/latest/ENV.txt if `make env` ran
#   <cmd>.txt        full stdout+stderr of the command
#   <cmd>.exit       its exit code
#   summary.md       a few grepped lines: what an agent pastes instead of the log
# stdout gets summary.md and the log's path, nothing else. exit code = the command's.
# the ledger holds command output only: never tokens, never sessions/ dumps.
set -u

[ $# -ge 1 ] || { echo "usage: scripts/ledger-run.sh <command...>" >&2; exit 2; }
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

sha=$(git rev-parse --short HEAD 2>/dev/null || echo nogit)
stamp=$(date -u +%Y%m%d-%H%M%S)
dir="ledger/$stamp-$sha"
n=1
while [ -e "$dir" ]; do dir="ledger/$stamp-$sha.$n"; n=$((n + 1)); done
mkdir -p "$dir"
[ -f ledger/latest/ENV.txt ] && cp ledger/latest/ENV.txt "$dir/ENV.txt"

name=$(printf '%s' "$*" | tr -c 'A-Za-z0-9._-' '-' | cut -c1-40)
log="$dir/$name.txt"

t0=$(date +%s.%N)
"$@" > "$log" 2>&1
rc=$?
t1=$(date +%s.%N)
echo "$rc" > "$dir/$name.exit"
wall=$(python3 -c "print(round($t1 - $t0, 2))" 2>/dev/null || echo ?)

{
    echo "# ledger $(basename "$dir")"
    echo
    echo "- command: \`$*\`"
    echo "- exit: $rc"
    echo "- wall_s: $wall"
    echo "- git: $sha $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo -)"
    # make test prints two "Ran N tests" lines: ROM first, then harness.
    awk '/^Ran [0-9]+ test/ { k++; split($0, a, " "); if (k == 1) print "- ROM: " a[2] " tests";
                                                     else if (k == 2) print "- harness: " a[2] " tests" }' "$log"
    grep -m1 '^bus_test:' "$log" | sed 's/^/- /'
    grep -m1 '^GREEN' "$log" | sed 's/^/- /'
    grep -m1 '^PERF' "$log" | sed 's/^/- /'
    grep -m1 '^FAILED' "$log" | sed 's/^/- /'
    if grep -qE '^(FAIL|ERROR):' "$log"; then
        echo
        echo "failing:"
        grep -E '^(FAIL|ERROR):' "$log" | head -20 | sed 's/^/    /'
    fi
    echo
    echo "full log: $log"
} > "$dir/summary.md"

ln -sfn "$(basename "$dir")" ledger/latest
cat "$dir/summary.md"
exit "$rc"
