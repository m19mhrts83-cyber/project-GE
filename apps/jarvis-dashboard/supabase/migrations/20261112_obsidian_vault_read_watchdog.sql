-- Short-lived ChatGPT read requests and Mac poller health for the local Obsidian Vault.
create table if not exists public.obsidian_vault_read_requests (
  id uuid primary key default gen_random_uuid(),
  request_type text not null check (request_type in ('search', 'excerpt')),
  request_payload jsonb not null,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'failed')),
  result jsonb,
  error_code text,
  created_at timestamptz not null default now(),
  claimed_at timestamptz,
  completed_at timestamptz,
  expires_at timestamptz not null default (now() + interval '15 minutes')
);

create index if not exists obsidian_vault_read_requests_pending_idx
  on public.obsidian_vault_read_requests (created_at)
  where status = 'pending';

create index if not exists obsidian_vault_read_requests_expiry_idx
  on public.obsidian_vault_read_requests (expires_at);

alter table public.obsidian_vault_read_requests enable row level security;
revoke all on public.obsidian_vault_read_requests from anon, authenticated;
grant select, insert, update, delete on public.obsidian_vault_read_requests to service_role;

comment on table public.obsidian_vault_read_requests is
  'Short-lived, allowlist-only read requests from ChatGPT to the Mac-local Obsidian Vault. Results are transient.';

create table if not exists public.obsidian_review_agent_status (
  agent_id text primary key check (agent_id = 'mac'),
  first_observed_at timestamptz not null default now(),
  monitor_started_at timestamptz,
  last_poll_at timestamptz,
  notified_state text not null default 'unknown'
    check (notified_state in ('unknown', 'online', 'offline')),
  state_changed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.obsidian_review_agent_status enable row level security;
revoke all on public.obsidian_review_agent_status from anon, authenticated;
grant select, insert, update on public.obsidian_review_agent_status to service_role;

insert into public.obsidian_review_agent_status (agent_id)
values ('mac')
on conflict (agent_id) do nothing;

comment on table public.obsidian_review_agent_status is
  'Mac review/read poller heartbeat and last Slack-notified state; no Vault content.';
