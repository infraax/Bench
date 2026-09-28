#!/bin/sh
# Re-fetch the 22 audited harness repos at the exact commits that were read on 2026-09-28.
# Clones land in research/clones/ (gitignored). Shallow, one commit each (~2.8 GB for all).
#   sh research/fetch.sh              # all repos
#   sh research/fetch.sh codex pi     # only names containing these words
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dest="$here/clones"
mkdir -p "$dest"
tab=$(printf '\t')
tail -n +2 "$here/repos.tsv" | while IFS="$tab" read -r name url sha date lic; do
  if [ "$#" -gt 0 ]; then
    hit=0
    for w in "$@"; do case "$name" in *"$w"*) hit=1 ;; esac; done
    [ "$hit" = 1 ] || continue
  fi
  short=$(printf '%.7s' "$sha")
  if [ -d "$dest/$name/.git" ] && [ "$(git -C "$dest/$name" rev-parse HEAD)" = "$sha" ]; then
    echo "ok     $name @ $short"
    continue
  fi
  rm -rf "$dest/$name"
  git init -q "$dest/$name"
  git -C "$dest/$name" fetch -q --depth 1 "$url" "$sha"
  git -C "$dest/$name" checkout -q FETCH_HEAD
  echo "fetch  $name @ $short ($date, $lic)"
done
