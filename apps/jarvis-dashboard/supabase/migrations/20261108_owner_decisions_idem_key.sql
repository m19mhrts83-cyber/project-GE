-- 判断ログ（owner_decisions）書き込み契約 v1 — 同じ判断の二重記録を防ぐ
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
--
-- 入口（Slack・loopware・ダッシュボード・KURASHIFT）は判断ごとに payload.idem_key を付ける。
-- 電波が切れて再送・二度押ししても1行だけ残るよう、一意の索引を張る。
-- idem_key の無い従来の行（triage トリガー等）は対象外。
-- 契約: apps/loopware/lib/decisionContract.ts

create unique index if not exists owner_decisions_idem_key_uidx
  on public.owner_decisions ((payload ->> 'idem_key'))
  where payload ? 'idem_key';

comment on column public.owner_decisions.payload is
  '契約 v1（apps/loopware/lib/decisionContract.ts）: v, idem_key, outcome(take/ng/hesitate/none/later/note), '
  'reason_tags[], scope, quality, stay_reason, next_step, applied_rules[], edit_ratio, timing{}, decide_ms, voice{segments[]} ほか入口ごとの値';
