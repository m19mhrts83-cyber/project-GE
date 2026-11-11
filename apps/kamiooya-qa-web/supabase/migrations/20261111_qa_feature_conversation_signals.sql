-- うまくいかなかった可能性のある会話（操作の記録から拾う、AIは使わない）の段階公開スイッチ。追加のみ。
-- まず松野さんだけ（answer_feedback と同じ名指し）。新しい表は無い。raimo-auth と Raimo 画面の反映が必要。
insert into public.qa_feature_flags(feature, stage, owner_ids, reviewer_ids, note)
select 'conversation_signals', 'owner', owner_ids, reviewer_ids, 'うまくいかなかった可能性のある会話（言い直し・続きの質問・聞き直し・断り・根拠未クリック）'
from public.qa_feature_flags where feature = 'answer_feedback'
on conflict (feature) do nothing;
