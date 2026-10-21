#!/usr/bin/env bash
# vesha's installer: clones vesha into ~/.local/share/vesha (its newest
# release) and links ~/.local/bin/vesha. No root.
#
#   curl -fsSL https://raw.githubusercontent.com/Theyashsawarkar/vesha/main/install.sh | bash
#   ./install.sh --setup     also install the claude wrapper and the watcher
set -euo pipefail
dest="${XDG_DATA_HOME:-$HOME/.local/share}/vesha"
bin="$HOME/.local/bin"
command -v git >/dev/null || { echo "vesha needs git" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null ||
  { echo "vesha needs Python 3.11 or newer" >&2; exit 1; }
if [ -d "$dest/.git" ]; then
  git -C "$dest" fetch -q --tags origin
else
  git clone -q https://github.com/Theyashsawarkar/vesha "$dest"
fi
latest=$(git -C "$dest" tag -l 'v*' --sort=-v:refname | head -1)
[ -n "$latest" ] && git -C "$dest" -c advice.detachedHead=false checkout -q "$latest"
mkdir -p "$bin"
ln -sfn "$dest/bin/vesha" "$bin/vesha"
echo "vesha ${latest:-(main)} installed: $bin/vesha"
case ":$PATH:" in *":$bin:"*) ;; *) echo "add $bin to your PATH (before /usr/bin)" ;; esac
if [ "${1:-}" = "--setup" ]; then
  "$bin/vesha" install-shim
  "$bin/vesha" service install
fi
echo "next: vesha add <name> --current   (the account Claude Code is signed in to), then vesha add <name> for each other one"
