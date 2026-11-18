# スキルの正本は `.agents/skills/`（2026-11-19〜）

Cursor・Codex・Antigravity は `.agents/skills/` をそのまま読む。Claude Code は `.claude/skills/` のリンク経由で同じものを読む。
新しいスキルは `.agents/skills/<名前>/SKILL.md` に置き、`sh scripts/link_shared_skills.sh` で Claude 用のリンクを張る。
ここ（`.cursor/skills/`）に同じスキルを置かない（二重になる）。経緯: `docs/AIエージェントチーム/49_共通ルール_AI使用量と入力_20261024.md` R14。
