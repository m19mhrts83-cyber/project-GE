# Todoist × 管理会社共有（Guest・要約フッター・転送メール評価）

更新: 2026-09-21  
依頼時の参照用。git 正本は同趣旨で `docs/Todoist_Guest共有_管理会社向け_20260921.md`。

## 方針（確定）

- **状況の継続確認はタスク側で足りる**（メール必須ではない）
- 相手の入力は **普段どおりのメール（estate）／LINE**（非対称ハブ）
- Jarvis が Todoist に起票・整理し、必要ならメール／LINE末尾に **状況要約フッター** を付ける
- **Todoist プロジェクト転送メールは相手に渡さない**（松野自分の転送専用）
- Guest（`PM_*` 共有ボード）は Beginner のプロジェクト枠が満杯のため **後回し**（Pro または枠空け後）

## 物件 × 管理会社（ラベル）

| 物件 | 管理会社 |
|---|---|
| GrandoleI | 主ミニテック。LEAF・Tcell も関与可 |
| GrandoleII | ホームプランナーのみ |
| キャラメル | Tcellのみ |

※「LEAF京都」は京都銀行の呼称であり **物件ではない**。

## Guest の見え方（将来）

| 項目 | 内容 |
|---|---|
| 見えるもの | 招待された `PM_LEAF` 等のタスクだけ |
| 見えないもの | 他プロジェクト・原価・家族タスク |
| 条件 | `PM_*` 作成 → Share 招待 → 相手が Todoist 無料アカウント → 承認 |
| 今のブロッカー | プロジェクト本数（Guest 席ではない） |

### 初回依頼（相手向け・短文）

1. 招待メール／リンクを開く  
2. 未登録なら業務用メールで無料アカウント作成  
3. 招待を承認  
4. 以降は同じプロジェクトを開けば最新一覧（書き込みは任意）

## 転送メール起票を相手に使わせない理由

相手が Todoist 宛だけに送ると、松野は Todoist 上では見えるが、**estate の往復スレ／やり取り.md から落ちやすい**。やり取り正本が分裂するため不採用。

## アドレス役割

| アドレス | 役割 |
|---|---|
| matsuno.estate@ | 対外 From／スレ正本 |
| admin@ | 受信集約・GenMail・ダッシュボード |
| jarvis@ | Todoist 通知読取（相手に渡さない） |
| Todoist 転送アドレス | 松野専用 |

## 運用コマンド

```bash
# 管理会社別・状況フッター
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_todoist_pm_status_footer.py --pm LEAF

# GenMail 要対応 → 提案（了承後 apply）
~/selenium_env/venv/bin/python scripts/jarvis_todoist_genmail_propose.py
```

パイロット候補（Guest 再開時）: LEAF／ホームプランナー。
