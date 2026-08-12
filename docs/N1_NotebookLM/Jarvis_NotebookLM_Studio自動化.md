# Jarvis × NotebookLM Studio 自動化

**目的**: Studio の Infographic／Slide Deck を Jarvis（headed Playwright）で操作する。  
**品質の本線**は引き続き NotebookLM Studio。Jarvis はボタン操作・プロンプト貼付・成果物保存を担当する。

関連: [運用まとめ_会話からの記録.md](運用まとめ_会話からの記録.md) §3.3（MCP だけでは Studio 不可）

---

## 役割分担

| 経路 | 担当 |
|---|---|
| NotebookLM MCP | チャット・text/url ソース・Audio Overview |
| **Studio ランナー**（本ドキュメント） | Infographic／Slide Deck の生成クリック・DL |
| Drive `200_NoteBookLM` | ソース正本・`★アウトプット/` 成果物 |

**MCP と Studio ランナーは Chrome プロファイルを分離する**（同時起動ロック対策）。

| 用途 | プロファイル |
|---|---|
| MCP | `~/Library/Application Support/notebooklm-mcp/chrome_profile` |
| Studio | `~/Library/Application Support/notebooklm-studio/chrome_profile` |

---

## 初回ログイン（Studio プロファイル）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python \
  scripts/jarvis_notebooklm_mcp_login.py --profile studio --headed
```

アカウントは **admin**（`NOTEBOOKLM_EMAIL` / `NOTEBOOKLM_PASSWORD`）。

---

## Phase 0 — UI 探査（生成は押さない）

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
/Users/matsunomasaharu2/selenium_env/venv/bin/python \
  scripts/jarvis_notebooklm_studio_probe.py \
  --notebook-url 'https://notebooklm.google.com/notebook/5a8dd67d-0789-48e2-b1e4-fb53484ffd2f'
```

- スクリーンショット・DOM ダンプ: `/tmp/notebooklm_studio_probe/`
- セレクタ候補の更新先: `config/notebooklm_studio_selectors.yaml`

---

## Phase 1〜2 — 生成＋保存

```bash
cd ~/git-repos && set -a && source .env.jarvis_private && set +a

# ドライラン（貼付まで・生成クリックなし）
/Users/matsunomasaharu2/selenium_env/venv/bin/python \
  scripts/jarvis_notebooklm_studio_run.py \
  --artifact infographic \
  --prompt-file '…/08_Studio修正プロンプト_20260812.md' \
  --prompt-section info \
  --dry-run

# 本番（生成クリック必須フラグ）
/Users/matsunomasaharu2/selenium_env/venv/bin/python \
  scripts/jarvis_notebooklm_studio_run.py \
  --artifact infographic \
  --prompt-file '…/08_Studio修正プロンプト_20260812.md' \
  --prompt-section info \
  --confirm-generate \
  --wait-and-save

# スライド
/Users/matsunomasaharu2/selenium_env/venv/bin/python \
  scripts/jarvis_notebooklm_studio_run.py \
  --artifact slide_deck \
  --prompt-file '…/08_Studio修正プロンプト_20260812.md' \
  --prompt-section slides \
  --confirm-generate \
  --wait-and-save
```

| フラグ | 意味 |
|---|---|
| `--dry-run` | 生成ボタンを押さない |
| `--confirm-generate` | 生成クリックを許可（必須・誤操作防止） |
| `--wait-and-save` | 完了待ち＋ Downloads → `★アウトプット/` |
| `--notebook-url` | 既定以外のノート |

設定: `config/notebooklm_studio.yaml`  
直近結果: `.jarvis_state/notebooklm_studio_run.json`

---

## トラブル

| 症状 | 対処 |
|---|---|
| プロファイルロック／TargetClosed | MCP 用 Chrome を終了し、studio プロファイルだけ使う |
| セレクタ不一致 | `studio_probe.py` 再実行 → selectors.yaml 更新 |
| ログイン切れ | `--profile studio` で再ログイン |
| 生成タイムアウト | `generate_timeout_sec` を延ばす／手動で完了確認 |

---

## 依頼の言い方（Cursor）

- 「Studio でインフォを直して（プロンプトは 08_Studio修正…）」
- 「北海道ノートの Studio を probe して」
- 「スライド再生成して ★アウトプット に保存して」

Jarvis は人間依頼起点のみ実行する（連打しない）。
