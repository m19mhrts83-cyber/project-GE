#!/bin/sh
# .agents/skills/<名前> を Claude Code 用に .claude/skills/<名前> へリンクする（正本は .agents/skills）。
# Cursor・Codex・Antigravity は .agents/skills を直接読むのでリンク不要。
set -e
cd "$(git rev-parse --show-toplevel)"
mkdir -p .claude/skills
for d in .agents/skills/*/; do
  n=$(basename "$d")
  [ -f "$d/SKILL.md" ] || continue
  t=".claude/skills/$n"
  if [ -L "$t" ] || [ ! -e "$t" ]; then ln -sfn "../../.agents/skills/$n" "$t"; else echo "skip（実体あり）: $t"; fi
done
# 正本から消えたスキルのリンクを片付ける
for l in .claude/skills/*; do [ -L "$l" ] && [ ! -e "$l" ] && rm "$l" && echo "removed stale: $l"; done
ls .claude/skills | wc -l
