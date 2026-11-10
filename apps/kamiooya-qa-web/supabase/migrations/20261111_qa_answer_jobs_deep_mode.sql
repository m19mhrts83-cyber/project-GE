-- (1) 「より詳しく調べる」（上位のモデルで答える）用の mode 'deep' を許可する（2026-11-11）。
alter table public.qa_answer_jobs drop constraint if exists qa_answer_jobs_mode_check;
alter table public.qa_answer_jobs add constraint qa_answer_jobs_mode_check check (mode in ('normal','semantic','fast','deep'));
