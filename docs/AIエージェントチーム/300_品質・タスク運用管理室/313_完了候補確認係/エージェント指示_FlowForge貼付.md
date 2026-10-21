# FlowForge「AIエージェントへの指示」貼付全文（313）

- 更新: 2026-10-21
- フロー: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_6s1nyBIKzluSsdgR-hs9IolD
- **ハブ正本**: 同フォルダ `flow.md` / `CLAUDE.md` / `PROGRESS.md` を優先。新規起票は 312。

---

# 業務自動化プロジェクトの伴走依頼

以下の業務フローを AIエージェント を使って自動化していきたいです。
**いきなり全自動を作るのではなく、私（初心者）と一緒に、簡単なところから段階的に進めてください。**
デスクトップアプリで作業フォルダを開いた状態で、この指示を貼り付けています。

---

## 対象の業務フロー

# Todoist完了候補確認（313）— 仕分け・close ワークフロー

完了相当をスキャンし、いい塩梅（L0確認のみ静かに／L1ダイジェスト見るだけ／L2個別了承）で仕分け、Slack へ出してから close する。確認のみは Jarvis が close 可。要判断は「閉じて N」まで残す。**新規 create はしない**（312）。

---

## 開始トリガー（複数・合流）

次のいずれかで起動し、**同じ**「スキャン→塩梅仕分け」に合流する。

1. **人依頼**: `/todoist-batch`・「Todoist掃除」「確認だけで消せる」「閉じて N」
2. **イベント**: 会話で完了相当／hawk `owner_confirm`／312の完了疑い列挙
3. **定期（運用C以降）**: オーナー確認列の取りこぼし保険（毎日固定ではない）

---

## 完了動線（出口3本）

| 経路 | 内容 |
|---|---|
| ① 要判断了承 → close | `#consult`／チャットで「閉じて N」→ `complete-task`（松野確認OK） |
| ② 確認のみ（L0） | 方針なし → オーナー確認経由で即 close（確認のみクローズ） |
| ③ バッチ／skill | `/todoist-batch`。末尾1ブロック報告 |

CLI: `scripts/jarvis_todoist_313_digest.py`（L1→#consult／`--auto-close-confirm`／`--apply --select N`）

---

## やらないこと

- L1一括 close、要判断の確認のみ扱い、コメント無し close
- 新規 create（→312）、秘密の再掲
- 家賃収支監査など別業務の混在

---

## 実装の正本

Mac CLI＋Cursor skill／ルール。FlowForge は設計図。停止: `JARVIS_TODOIST_313_DIGEST_DISABLE=1`
