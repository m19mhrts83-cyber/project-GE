-- Fix Supabase Security Advisor critical: rls_disabled_in_public
-- Target project: kamiooya-qa (ref mwubzgefkkjjbingrmqu)
--
-- Applied to production 2026-07-22 (Jarvis). App/ingest/Edge use service_role only.

begin;

alter table if exists public.users enable row level security;
alter table if exists public.comments enable row level security;
alter table if exists public.suggested_questions enable row level security;
alter table if exists public.chat_sessions enable row level security;
alter table if exists public.chat_messages enable row level security;
alter table if exists public.knowledge_sources enable row level security;
alter table if exists public.knowledge_chunks enable row level security;
alter table if exists public.jarvis_heartbeat enable row level security;
alter table if exists public.app_qa_search_events enable row level security;

revoke all on table public.users from anon, authenticated;
revoke all on table public.comments from anon, authenticated;
revoke all on table public.suggested_questions from anon, authenticated;
revoke all on table public.chat_sessions from anon, authenticated;
revoke all on table public.chat_messages from anon, authenticated;
revoke all on table public.knowledge_sources from anon, authenticated;
revoke all on table public.knowledge_chunks from anon, authenticated;
revoke all on table public.jarvis_heartbeat from anon, authenticated;
revoke all on table public.app_qa_search_events from anon, authenticated;
revoke all on table public.app_qa_search_mode_daily from anon, authenticated;

grant select, insert, update, delete on table public.users to service_role;
grant select, insert, update, delete on table public.comments to service_role;
grant select, insert, update, delete on table public.suggested_questions to service_role;
grant select, insert, update, delete on table public.chat_sessions to service_role;
grant select, insert, update, delete on table public.chat_messages to service_role;
grant select, insert, update, delete on table public.knowledge_sources to service_role;
grant select, insert, update, delete on table public.knowledge_chunks to service_role;
grant select, insert, update, delete on table public.jarvis_heartbeat to service_role;
grant select, insert, update, delete on table public.app_qa_search_events to service_role;
grant select on table public.app_qa_search_mode_daily to service_role;
grant usage, select on all sequences in schema public to service_role;

-- Advisor WARN: function_search_path_mutable
alter function public.match_comments_semantic(vector, double precision, integer)
  set search_path = public, extensions;
alter function public.match_chunks_semantic(vector, double precision, integer)
  set search_path = public, extensions;

commit;
