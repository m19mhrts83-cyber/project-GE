-- Mac 見張り: 2 回連続で止まりと判定された時だけ通知するための連続回数（2026-11-28 松野さん承認）。
-- 実データは入れない（回数だけ）。適用してから route をデプロイすること。
alter table public.mac_watch_status
  add column if not exists offline_streak integer not null default 0;
