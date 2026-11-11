-- まとめてキーワード検索（全データソース横断）の段階公開スイッチ。追加のみ。
-- まず松野さんだけ（answer_feedback と同じ名指し）。画面だけの機能で、新しい API や表は無い。
insert into public.qa_feature_flags(feature, stage, owner_ids, reviewer_ids, note)
select 'keyword_all', 'owner', owner_ids, reviewer_ids, 'まとめてキーワード検索（コメント・動画・講座ページ・オプチャを横断。AIは使わない）'
from public.qa_feature_flags where feature = 'answer_feedback'
on conflict (feature) do nothing;
