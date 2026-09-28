#!/bin/sh
# SPDX-License-Identifier: MIT OR Apache-2.0
# bootstrap-debian.sh — the whole build/test prerequisite list, pinned by name. run it yourself;
# nothing else in this tree installs packages. no scanners, no extras.
set -eu
PKGS="build-essential python3 git"
echo "installing: $PKGS"
if [ "$(id -u)" -eq 0 ]; then apt-get update && apt-get install -y $PKGS
else sudo apt-get update && sudo apt-get install -y $PKGS; fi
