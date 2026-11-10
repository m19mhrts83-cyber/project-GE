-- (2) 回答の評価に「理由の選択肢」を追加（2026-11-10 松野さん）。追加のみ。
-- 超いいね: accurate 正確 / practical 実践に使える / clear 分かりやすい / source 根拠・出典 / new_view 新しい視点
-- 悪いね:   wrong 間違い・古い / off_topic 質問とずれ / vague 一般論 / hard_to_read 分かりにくい / no_source 根拠不足
-- 選択肢以外は comment（その他・任意）に入る。値の検査はサーバー（answerFeedback.ts）でも行う。
alter table public.qa_answer_feedback
  add column if not exists reasons text[] not null default '{}';
alter table public.qa_answer_feedback
  drop constraint if exists qa_answer_feedback_reasons_check;
alter table public.qa_answer_feedback
  add constraint qa_answer_feedback_reasons_check check (
    cardinality(reasons) <= 5 and (
      (rating = 'great' and reasons <@ array['accurate','practical','clear','source','new_view']::text[]) or
      (rating = 'bad'   and reasons <@ array['wrong','off_topic','vague','hard_to_read','no_source']::text[]) or
      (rating = 'good'  and cardinality(reasons) = 0)
    )
  );
