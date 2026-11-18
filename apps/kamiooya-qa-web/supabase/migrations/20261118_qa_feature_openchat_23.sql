-- 23番オプチャ（23再生AP/MSにチャレンジ!!）は成果達成者限定。会員全員には出さず、まず松野さんだけに見せる（2026-11-18 松野さん）。
-- 判定は semantic-search（lib/openchatAccess.ts）。スイッチが無い・読めないときは誰にも見せない。
insert into public.qa_feature_flags(feature, stage, owner_ids, reviewer_ids, note)
select 'openchat_23', 'owner', owner_ids, '{}'::text[], '23番オプチャ（成果達成者限定）を見られる人'
from public.qa_feature_flags where feature = 'openchat_threads'
on conflict (feature) do nothing;
