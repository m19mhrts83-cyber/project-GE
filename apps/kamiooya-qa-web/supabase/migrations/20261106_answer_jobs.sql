create table if not exists public.qa_answer_jobs (
 id uuid primary key default gen_random_uuid(),
 user_id text not null,chat_id text not null,request_id uuid not null,request_hash text not null,
 auth_version text not null,parent_session_ref text not null,
 mode text not null check(mode in ('normal','semantic','fast')),query text not null check(length(query) between 1 and 4000),
 status text not null default 'running' check(status in ('running','done','failed')),
 deadline_at timestamptz not null,created_at timestamptz not null default now(),finished_at timestamptz,
 result jsonb,error_code text,unique(user_id,request_id)
);
create index if not exists qa_answer_jobs_active on public.qa_answer_jobs(user_id,status,deadline_at);
alter table public.qa_answer_jobs enable row level security;
revoke all on public.qa_answer_jobs from public,anon,authenticated;
grant select,insert,update on public.qa_answer_jobs to service_role;

create or replace function public.qa_admit_answer_job(job jsonb)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare old public.qa_answer_jobs;fresh public.qa_answer_jobs;uid text:=job->>'user_id';
begin
 if uid is null or uid='' or length(job->>'auth_version')<>64 or length(job->>'parent_session_ref')<>64
  or (job->>'deadline_at')::timestamptz>now()+interval '6 minutes' or (job->>'deadline_at')::timestamptz<=now()
 then raise exception 'invalid_answer_job'; end if;
 perform pg_advisory_xact_lock(hashtextextended(uid,0));
 select * into old from public.qa_answer_jobs where user_id=uid and request_id=(job->>'request_id')::uuid;
 if found then
  if old.request_hash<>job->>'request_hash' then return jsonb_build_object('conflict',true); end if;
  return jsonb_build_object('job',to_jsonb(old),'created',false);
 end if;
 select * into old from public.qa_answer_jobs where user_id=uid and status='running' and deadline_at>now() order by created_at desc limit 1;
 if found then
  if old.chat_id=job->>'chat_id' and old.request_hash=job->>'request_hash' and old.auth_version=job->>'auth_version'
   then return jsonb_build_object('job',to_jsonb(old),'created',false); end if;
  return jsonb_build_object('busy',true);
 end if;
 insert into public.qa_answer_jobs(user_id,chat_id,request_id,request_hash,auth_version,parent_session_ref,mode,query,deadline_at)
 values(uid,job->>'chat_id',(job->>'request_id')::uuid,job->>'request_hash',job->>'auth_version',job->>'parent_session_ref',job->>'mode',job->>'query',(job->>'deadline_at')::timestamptz)
 returning * into fresh;
 return jsonb_build_object('job',to_jsonb(fresh),'created',true);
end $$;
revoke all on function public.qa_admit_answer_job(jsonb) from public,anon,authenticated;
grant execute on function public.qa_admit_answer_job(jsonb) to service_role;
notify pgrst,'reload schema';
