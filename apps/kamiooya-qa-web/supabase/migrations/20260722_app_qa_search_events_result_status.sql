-- Phase 14-1: search event result status for ops visibility
alter table public.app_qa_search_events
  add column if not exists result_status text not null default 'ok';

alter table public.app_qa_search_events
  add column if not exists error_message text;

comment on column public.app_qa_search_events.result_status is
  'ok | error | disabled | rate_limited';
comment on column public.app_qa_search_events.error_message is
  'short error or skip reason';
