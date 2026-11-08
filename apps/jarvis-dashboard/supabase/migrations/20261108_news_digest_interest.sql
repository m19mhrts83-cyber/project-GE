-- ニュース配信（Banto Webhook）＋興味フィードバック
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
-- 2026-11-08

create table if not exists public.news_feeds (
  feed_id text primary key,
  title text not null,
  schedule_note text,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.news_posts (
  id bigserial primary key,
  feed_id text not null references public.news_feeds (feed_id),
  item_key text not null,
  slack_channel text not null default 'C0C866FNU3C',
  slack_ts text not null,
  posted_at timestamptz,
  title text,
  topics jsonb not null default '[]'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (feed_id, item_key),
  unique (slack_channel, slack_ts)
);

create index if not exists news_posts_posted_at_idx
  on public.news_posts (posted_at desc nulls last);
create index if not exists news_posts_feed_idx
  on public.news_posts (feed_id, posted_at desc nulls last);

create table if not exists public.news_interest_events (
  id bigserial primary key,
  post_id bigint not null references public.news_posts (id) on delete cascade,
  kind text not null, -- plus1 / minus1 / comment
  actor text,
  text text,
  captured_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  unique (post_id, kind, actor)
);

create index if not exists news_interest_events_captured_idx
  on public.news_interest_events (captured_at desc);
create index if not exists news_interest_events_post_idx
  on public.news_interest_events (post_id, kind);

alter table public.news_feeds enable row level security;
alter table public.news_posts enable row level security;
alter table public.news_interest_events enable row level security;

revoke all on table public.news_feeds from anon, authenticated;
revoke all on table public.news_posts from anon, authenticated;
revoke all on table public.news_interest_events from anon, authenticated;

grant select, insert, update, delete on table public.news_feeds
  to authenticated, service_role;
grant select, insert, update, delete on table public.news_posts
  to authenticated, service_role;
grant select, insert, update, delete on table public.news_interest_events
  to authenticated, service_role;

grant usage, select on sequence public.news_posts_id_seq
  to authenticated, service_role;
grant usage, select on sequence public.news_interest_events_id_seq
  to authenticated, service_role;

insert into public.news_feeds (feed_id, title, schedule_note) values
  ('cursor_friday', 'Friday Cursor Automation Brief', '金曜 23:08ごろ'),
  ('ai_weekly', 'AI源流・未来動向ウィークリーブリーフ', '日曜 19:00'),
  ('space_defense_daily', '宇宙・防衛・AIデイリーブリーフ', '毎日 22:30'),
  ('defense_mgr', '防衛宇宙・製造管理職 外部環境ブリーフ', '毎日 22:30')
on conflict (feed_id) do update set
  title = excluded.title,
  schedule_note = excluded.schedule_note,
  updated_at = now();
