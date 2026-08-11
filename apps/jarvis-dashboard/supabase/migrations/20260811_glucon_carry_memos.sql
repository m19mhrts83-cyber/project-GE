-- グルコン次月報告メモ（周期をまたいで残す。下書き payload とは独立）

create table if not exists public.glucon_carry_memos (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null default '',
  kind_hint text not null default 'result'
    check (kind_hint in ('result', 'activity', 'either')),
  status text not null default 'open'
    check (status in ('open', 'used', 'discarded')),
  parked_period_key text not null,
  available_from_period_key text not null,
  used_in_period_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists glucon_carry_memos_status_idx
  on public.glucon_carry_memos (status, available_from_period_key);

comment on table public.glucon_carry_memos is
  'グルコン次月報告メモ。parked 周期では生成に入れず、available_from 以降の下書き生成へ注入';

alter table public.glucon_carry_memos enable row level security;

drop policy if exists glucon_carry_memos_auth_all on public.glucon_carry_memos;
create policy glucon_carry_memos_auth_all on public.glucon_carry_memos
  for all to authenticated
  using (true)
  with check (true);

insert into public.glucon_carry_memos (
  title, body, kind_hint, status,
  parked_period_key, available_from_period_key
)
select
  'スマートロックまとめ資料の見直し共有',
  '成果報告で言ってもよかったが今回は見送り。以前 Nature Remo と Alexa のスマートホーム資料が役立ったので、今回のスマートロックまとめも結果を踏まえて見直し、次月にコミュニティ共有する。',
  'result',
  'open',
  '2026-08',
  '2026-09'
where not exists (
  select 1 from public.glucon_carry_memos
  where title = 'スマートロックまとめ資料の見直し共有'
);
