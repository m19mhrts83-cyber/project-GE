-- Quiet Edge: 治療枠を最大9回想定。日程未定は planned + scheduled_at null
alter table public.vital_treatment_events
  alter column scheduled_at drop not null;

alter table public.vital_treatment_events
  drop constraint if exists vital_treatment_events_status_check;

alter table public.vital_treatment_events
  add constraint vital_treatment_events_status_check
  check (status = any (array['done'::text, 'scheduled'::text, 'cancelled'::text, 'planned'::text]));
