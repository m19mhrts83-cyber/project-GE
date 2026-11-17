-- スマホ縦の表示（メニュー縦並び・LINEオプチャ一覧のカード表示）をスイッチで限定公開にする（2026-11-18 松野さん）
-- PR #459 をスイッチなしで全員に出してしまったため、松野さんだけに戻す。画面側は html.ff-mobile-layout のときだけ効く。
insert into public.qa_feature_flags(feature, stage, owner_ids, reviewer_ids, note)
select 'mobile_layout', 'owner', owner_ids, '{}'::text[], 'スマホ縦の表示（メニュー縦並び・LINEオプチャ一覧のカード表示）'
from public.qa_feature_flags where feature = 'openchat_threads'
on conflict (feature) do nothing;
