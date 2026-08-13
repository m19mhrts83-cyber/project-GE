-- 法人申告（Knees bee メールPDF）を税サイクルに載せる
alter table public.kurashift_tax_cases drop constraint if exists kurashift_tax_cases_scope_check;
alter table public.kurashift_tax_cases add constraint kurashift_tax_cases_scope_check
  check (scope in ('personal', 'corporate'));

alter table public.kurashift_tax_evidence add column if not exists scope text not null default 'personal';
alter table public.kurashift_tax_evidence drop constraint if exists kurashift_tax_evidence_scope_check;
alter table public.kurashift_tax_evidence add constraint kurashift_tax_evidence_scope_check
  check (scope in ('personal', 'corporate'));

create index if not exists kurashift_tax_evidence_scope_year_idx
  on public.kurashift_tax_evidence (scope, fiscal_year desc);
