# PROGRESS — 管理会社向け朝便返信下書き

作業再開時は先にこのファイル → 次に `CLAUDE.md` を読む。

## 2026-10-11（Phase3 Graph／GHA）

- **やったこと**: 正本書込を Graph PUT 化。`jarvis_gha_reply_draft_211.py`＋workflow `jarvis-reply-draft-211.yml`（07:30 JST）。見積Bは Graph 列挙。書込プローブ成功。refresh 回転を Secrets へ反映。
- **できたファイル**:
  - `scripts/jarvis_gha_reply_draft_211.py`
  - `.github/workflows/jarvis-reply-draft-211.yml`
  - `jarvis_onedrive_graph.list_children_graph*`
  - `apply_draft_to_partner` Graph 本線
- **疎通**: probe_ok / PUT `.jarvis_graph_write_probe.txt` / PM4フォルダ materialize dry-run
- **GHA dry-run**: 成功（[run 38094845121](https://github.com/m19mhrts83-cyber/project-GE/actions/runs/38094845121)）— 起案候補2／見積B待ち1／書込なし
- **次の一手**: 明朝の schedule 本番、または `gh workflow run … -f dry_run=false`。緑が続いたら Mac launchd uninstall
- **状態**: Phase3 本線稼働前（dry-run 緑）。作業フロー反映済

## 2026-10-11（Phase2 朝便定常＋見積B）

- **やったこと**: `jarvis_reply_draft_211.py` を Phase2 化。Mac launchd 雛形。
- **Phase1 送信クローズ**: ミニテック Gmail／Tcell LINE＋record-only
- **状態**: Phase2 完了 → Phase3 へ

## 2026-10-11（具体化・正本起案）

- Phase1 書込＋Slack 検証完了（ログ: `logs/20261011_phase1_drafts.md`）
