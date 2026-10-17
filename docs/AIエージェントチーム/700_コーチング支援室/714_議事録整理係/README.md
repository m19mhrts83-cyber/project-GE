# 【設計中】714 議事録整理係

Genspark／JPR の録音から「Notion に残す価値あり」を提案し、了承後に電話・面談 Inbox へページ化する係。

| 項目 | 内容 |
|---|---|
| 本線 | `scripts/jarvis_meeting_minutes_curate.py` |
| Hot | Genspark（`jarvis_genspark_meeting_fetch.py`） |
| Warm | Notion `_Inbox`（[`config/notion_phone_meeting.yaml`](../../../config/notion_phone_meeting.yaml)） |
| 除外 | 家族会議週次（711／`jarvis-family-meeting-weekly`） |
| 確認 | **無言作成禁止**。提案 → 了承 → `--apply` |
| 組織図 | [ビルダー共有](https://agent-team-builder-teal.vercel.app/s/uksxiDIzE1AEckKH) |
| 指示書 | [`CLAUDE.md`](./CLAUDE.md) |
| 停止 | `JARVIS_MEETING_MINUTES_CURATE_DISABLE=1` |
