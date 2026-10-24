# TASK — 314 業務品質監査係

規格: [`30_共通Agentフォルダ規格_BCP`](../../30_共通Agentフォルダ規格_BCP_20261017.md)

| 項目 | 値 |
|---|---|
| task_id | weekly-review-YYYYMMDD（毎週） |
| agent_id | 314 |
| executor | launchd（機械チェック）／claude_code（レビュー） |
| status | running（毎週土曜） |
| started_at | 2026-10-24 |
| finished_at | |

## 依頼

今週 main に入った仕組み・プログラムをレビューし、問題があれば AI 使用量が少なく効果的な方法に直す。見た観点と処置を報告する。手順は [CLAUDE.md](./CLAUDE.md) §6。

## 完了条件

- [ ] `output/YYYYMMDD_週次レビュー.md` がある（§7 の型）
- [ ] 修正があれば PR があり、`scripts/tests` が通っている
- [ ] 人の対応待ちが MD に列挙され、先週分の持ち越しが消し込まれている
