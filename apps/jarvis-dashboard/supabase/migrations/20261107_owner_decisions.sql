-- 松野さんの判断ログ（owner_decisions）
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
--
-- 目的: 社員の提案（下書き・未返信判定・起票案・完了候補）に対して松野さんが
--       どう判断したか（送った／直して送った／見送った／後で）を1か所に残し、
--       週1回 314 業務品質監査係がこれを読んでプロンプトやコードを直す。
--
-- 書き込み経路:
--   1. triage_items の status が pending から変わったとき → トリガーで自動記録
--      （ダッシュボード・Slack リンク・Slack ボタンのどれから閉じても残る）
--      あわせて comm_items（台帳）の work_status も閉じる
--   2. Todoist 312 起票／313 完了・延期／S9 採用・見送り → アプリ側 lib/ownerDecisionLog.ts
--
-- 記録の失敗で本線（status 更新）は止めない（exception → warning）。
-- 個人情報が入るため service_role のみ GRANT。

create table if not exists public.owner_decisions (
  id bigserial primary key,
  decided_at timestamptz not null default now(),
  surface text not null,              -- triage / todoist_312 / todoist_313 / s9
  action text not null,               -- sent / skipped / snoozed / done / create / dismiss / close / reschedule / adopt / skip
  source text,                        -- slack_button / slack_link / dashboard_or_script
  employee text,                      -- 提案した社員（111 / 116 / 211 / 312 / 313 / S9 …。triage は週次スクリプトが lane から補う）
  target_type text not null,          -- triage_item / todoist_task / s9_candidate
  target_id text not null,
  lane text,
  kind text,
  channel text,
  partner text,
  folder text,
  subject text,
  comm_item_id uuid,
  prev_status text,
  ai_proposal text,                   -- 判断前の下書き・提案
  final_text text,                    -- 送った本文（sent のとき）
  edited boolean,                     -- 下書きを直して送ったか
  note text,                          -- 見送り理由など
  payload jsonb not null default '{}'::jsonb,
  review_week text,                   -- 314 が週次で読んだ週（例 2026-W46）
  review_note text,
  created_at timestamptz not null default now()
);

create index if not exists owner_decisions_time_idx
  on public.owner_decisions (decided_at desc);
create index if not exists owner_decisions_surface_time_idx
  on public.owner_decisions (surface, decided_at desc);
create index if not exists owner_decisions_target_idx
  on public.owner_decisions (target_type, target_id);

alter table public.owner_decisions enable row level security;
revoke all on table public.owner_decisions from anon, authenticated;
grant select, insert, update, delete on table public.owner_decisions to service_role;
grant usage, select on sequence public.owner_decisions_id_seq to service_role;

-- ---------------------------------------------------------------- triage_items → 判断ログ + 台帳
create or replace function public.triage_items_log_owner_decision()
returns trigger language plpgsql
security definer
set search_path = public
as $$
declare
  v_source text := 'dashboard_or_script';
  v_note text;
  v_work text;
begin
  if coalesce(old.status, 'pending') <> 'pending'
     or coalesce(new.status, 'pending') = 'pending' then
    return new;
  end if;

  begin
    if (new.payload -> 'slack_ma_action') is distinct from (old.payload -> 'slack_ma_action') then
      v_source := coalesce(new.payload -> 'slack_ma_action' ->> 'source', 'slack');
    elsif (new.payload -> 'slack_vr_action') is distinct from (old.payload -> 'slack_vr_action') then
      v_source := coalesce(new.payload -> 'slack_vr_action' ->> 'source', 'slack');
    end if;

    v_note := coalesce(
      new.payload ->> 'skip_reason',
      new.payload -> 'slack_ma_action' ->> 'reason',
      new.payload -> 'slack_vr_action' ->> 'reason'
    );

    insert into public.owner_decisions (
      surface, action, source, target_type, target_id,
      lane, kind, channel, partner, folder, subject, comm_item_id,
      prev_status, ai_proposal, final_text, edited, note, payload
    ) values (
      'triage', new.status, v_source, 'triage_item', new.id,
      new.lane, new.kind, new.channel, new.partner, new.folder, new.subject, new.comm_item_id,
      old.status,
      old.draft_text,
      case when new.status = 'sent' then new.draft_text end,
      case
        when new.status = 'sent' and old.draft_text is not null
          then new.draft_text is distinct from old.draft_text
      end,
      v_note,
      jsonb_strip_nulls(jsonb_build_object(
        'priority', new.priority,
        'summary', left(coalesce(new.summary, ''), 500),
        'slack_ma_action', new.payload -> 'slack_ma_action',
        'slack_vr_action', new.payload -> 'slack_vr_action',
        'manual_reply', new.payload -> 'manual_reply'
      ))
    );

    if new.comm_item_id is not null then
      v_work := case new.status
        when 'sent' then 'done'
        when 'done' then 'done'
        when 'skipped' then 'no_action'
        when 'snoozed' then 'waiting'
      end;
      if v_work is not null then
        update public.comm_items
           set work_status = v_work
         where id = new.comm_item_id
           and work_status in ('new', 'needs_reply', 'drafted');
      end if;
    end if;
  exception when others then
    raise warning 'owner_decisions log skipped: %', sqlerrm;
  end;
  return new;
end;
$$;

revoke all on function public.triage_items_log_owner_decision() from public, anon, authenticated;

drop trigger if exists triage_items_log_owner_decision on public.triage_items;
create trigger triage_items_log_owner_decision
  after update of status on public.triage_items
  for each row execute function public.triage_items_log_owner_decision();
