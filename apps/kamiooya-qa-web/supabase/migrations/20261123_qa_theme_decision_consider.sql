-- (4) 講座テーマ案の判断に「検討案として採用」(consider) を足す（2026-11-23 松野さん）。
-- 次の作り直しで、検討案を踏まえたより具体的な案を出す（scripts/course_theme/weekly_round.py）。
alter table public.qa_theme_decisions drop constraint if exists qa_theme_decisions_choice_check;
alter table public.qa_theme_decisions add constraint qa_theme_decisions_choice_check
  check (choice in ('adopt','revise','consider','reject'));
