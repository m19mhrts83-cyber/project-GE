# Todoist × 管理会社共有（Guest・要約フッター・転送メール評価）

更新: 2026-09-22  
依頼時の参照用。git 正本は同趣旨で `docs/Todoist_Guest共有_管理会社向け_20260921.md`。

## 方針（確定）

- **状況の継続確認はタスク側で足りる**（メール必須ではない）
- 相手の入力は **普段どおりのメール（estate）／LINE**（非対称ハブ）
- Jarvis が Todoist に起票・整理し、必要ならメール／LINE末尾に **状況要約フッター** を付ける
- **Todoist プロジェクト転送メールは相手に渡さない**（松野自分の転送専用）
- Guest（`PM_*` 共有ボード）: **Pro 後に骨格作成済**（2026-09-22）。招待メール送信は対外了承後

## 物件 × 管理会社（ラベル）

| 物件 | 管理会社 |
|---|---|
| GrandoleI | 主ミニテック。LEAF・Tcell も関与可 |
| GrandoleII | ホームプランナーのみ |
| キャラメル | Tcellのみ |

※「LEAF京都」は京都銀行の呼称であり **物件ではない**。

## Guest パイロット（Phase 4・骨格済）

| プロジェクト | 管理会社 | URL（admin 上） |
|---|---|---|
| `PM_LEAF` | LEAF | https://app.todoist.com/app/project/6hc28xHhRFvr7P9H |
| `PM_ホームプランナー` | ホームプランナー | https://app.todoist.com/app/project/6hc28xj8wcC4X442 |

YAML: `config/todoist_projects.yaml` → `pm_share` / `pm_guest_projects`

| 項目 | 内容 |
|---|---|
| 見えるもの | 招待された `PM_*` のタスクだけ |
| 見えないもの | 所有物件全体・原価・家族・他レーン |
| 条件 | Share 招待 → 相手が Todoist 無料アカウント → 承認 |
| ブロッカー（旧） | Beginner プロジェクト枠 → **解除済（Pro）** |
| 次の一手 | **パートナー確認のついでに Jarvis が招待を提案** → 了承後に admin UI で Share。成功ゲート: 週1接触 or フッター運用が楽 |

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
# 管理会社別・状況フッター（Guest URL 設定後は末尾に共有案内可）
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
~/selenium_env/venv/bin/python scripts/jarvis_todoist_pm_status_footer.py --pm LEAF

# 会話駆動ステータス提案（Phase5）
~/selenium_env/venv/bin/python scripts/jarvis_todoist_conv_status_propose.py --text '対応完了しました'
```

パイロット: LEAF／ホームプランナー（招待は了承後）。
