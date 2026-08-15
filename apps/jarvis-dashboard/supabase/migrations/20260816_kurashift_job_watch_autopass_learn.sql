-- KURASHIFT: job watch / inquiry sending / auto_pass learn
-- Project: jarvis-dashboard

-- Realtime 加速用（本線はポーリング。未追加だと Realtime は無音）
do $$
begin
  alter publication supabase_realtime add table public.kurashift_jobs;
exception
  when duplicate_object then null;
  when undefined_object then null;
  when others then
    raise notice 'realtime publication skip: %', sqlerrm;
end $$;

-- inquiry_status に sending を追加
alter table public.kurashift_re_deals
  drop constraint if exists kurashift_re_deals_inquiry_status_check;

alter table public.kurashift_re_deals
  add constraint kurashift_re_deals_inquiry_status_check
  check (inquiry_status in (
    'none', 'draft', 'sending', 'sent', 'awaiting_reply', 'has_reply'
  ));

-- 自動見送り学習（正本）
create table if not exists public.kurashift_auto_pass_learn (
  reason text primary key,
  confirm_count int not null default 0,
  reject_count int not null default 0,
  allowlisted_at timestamptz,
  updated_at timestamptz not null default now()
);

alter table public.kurashift_auto_pass_learn enable row level security;

drop policy if exists kurashift_auto_pass_learn_auth_all on public.kurashift_auto_pass_learn;
create policy kurashift_auto_pass_learn_auth_all
  on public.kurashift_auto_pass_learn
  for all to authenticated
  using (true)
  with check (true);
