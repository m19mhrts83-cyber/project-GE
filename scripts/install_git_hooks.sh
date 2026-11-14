#!/bin/sh
# このリポの git hook（scripts/hooks/）を使うようにする。Mac・各 worktree で 1 回。
set -eu
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath scripts/hooks
echo "hooksPath=scripts/hooks（pre-commit: 公開リポ ガード）"
