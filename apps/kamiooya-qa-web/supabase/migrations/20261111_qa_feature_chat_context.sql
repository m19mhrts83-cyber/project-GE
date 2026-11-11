-- 同じチャットの直前のやり取り（質問・回答）を踏まえて探す・答える（意味検索／より詳しく調べる）の段階公開スイッチ。追加のみ。
-- まず松野さんだけ（answer_feedback と同じ名指し）。新しい表や API は無い。raimo-auth の反映が必要。
insert into public.qa_feature_flags(feature, stage, owner_ids, reviewer_ids, note)
select 'chat_context', 'owner', owner_ids, reviewer_ids, '同じチャットの直前のやり取りを踏まえて検索・回答（「また詳しく」が前の質問のテーマで深掘りになる）'
from public.qa_feature_flags where feature = 'answer_feedback'
on conflict (feature) do nothing;
