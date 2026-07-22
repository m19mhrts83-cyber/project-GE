-- Fix Supabase Security Advisor critical: rls_disabled_in_public
-- Target project: kamiooya-qa (ref mwubzgefkkjjbingrmqu)
--
-- Context:
--   schema.sql previously granted CRUD to anon/authenticated without RLS.
--   App routes and ingest scripts use SUPABASE_SERVICE_ROLE_KEY only.
--
-- Apply in Dashboard SQL Editor, or via `supabase db query` / MCP execute_sql.
-- After apply, re-run Database → Security Advisor and confirm criticals are cleared.

begin;

alter table if exists public.users enable row level security;
alter table if exists public.comments enable row level security;
alter table if exists public.suggested_questions enable row level security;
alter table if exists public.chat_sessions enable row level security;
alter table if exists public.chat_messages enable row level security;
alter table if exists public.knowledge_sources enable row level security;
alter table if exists public.knowledge_chunks enable row level security;
alter table if exists public.jarvis_heartbeat enable row level security;

revoke all on table public.users from anon, authenticated;
revoke all on table public.comments from anon, authenticated;
revoke all on table public.suggested_questions from anon, authenticated;
revoke all on table public.chat_sessions from anon, authenticated;
revoke all on table public.chat_messages from anon, authenticated;
revoke all on table public.knowledge_sources from anon, authenticated;
revoke all on table public.knowledge_chunks from anon, authenticated;
revoke all on table public.jarvis_heartbeat from anon, authenticated;

grant select, insert, update, delete on table public.users to service_role;
grant select, insert, update, delete on table public.comments to service_role;
grant select, insert, update, delete on table public.suggested_questions to service_role;
grant select, insert, update, delete on table public.chat_sessions to service_role;
grant select, insert, update, delete on table public.chat_messages to service_role;
grant select, insert, update, delete on table public.knowledge_sources to service_role;
grant select, insert, update, delete on table public.knowledge_chunks to service_role;
grant select, insert, update, delete on table public.jarvis_heartbeat to service_role;
grant usage, select on all sequences in schema public to service_role;

commit;
