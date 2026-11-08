-- 判断ログ（owner_decisions）— triage トリガーを契約 v1 に合わせる（ループウェア段階2）
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
--
-- 変更点（20261107_owner_decisions.sql の関数を置き換え。表は変えない）:
--   - payload.applied_rules: Slack に出したとき（116）と下書きを書いたとき（211, payload.draft_rules）に
--     効かせたルール番号を写す（効いたかを週次で数える）
--   - payload.ai_score: そのときの並び順の点数
--   - payload.v / outcome（採った・見送った・迷った…）
--   - loopware 判断デスクからの判断（payload.loopware_action）を入口 loopware として数える
--   - source を slack / loopware / dashboard / kurashift / script に寄せ、元の名前は payload.source_detail
-- 契約: apps/loopware/lib/decisionContract.ts

create or replace function public.triage_items_log_owner_decision()
returns trigger language plpgsql
security definer
set search_path = public
as $$
declare
  v_source text := 'dashboard_or_script';
  v_note text;
  v_work text;
  v_detail text;
  v_outcome text;
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
    elsif (new.payload -> 'loopware_action') is distinct from (old.payload -> 'loopware_action') then
      -- loopware 判断デスク（/desk）・KURASHIFT からの判断
      v_source := coalesce(new.payload -> 'loopware_action' ->> 'source', 'loopware');
    end if;

    -- 契約 v1: 入口は slack / loopware / dashboard / kurashift / script に寄せ、元の名前は source_detail に
    v_detail := v_source;
    v_source := case
      when v_source like 'slack%' then 'slack'
      when v_source like 'loopware%' then 'loopware'
      when v_source like 'kurashift%' then 'kurashift'
      when v_source like 'dashboard%' then 'dashboard'
      else 'script'
    end;
    v_outcome := case new.status
      when 'sent' then 'take'
      when 'done' then 'take'
      when 'todoist' then 'take'
      when 'skipped' then 'ng'
      when 'hesitated' then 'hesitate'
      when 'snoozed' then 'later'
      else 'note'
    end;

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
        'v', 1,
        'outcome', v_outcome,
        'source_detail', nullif(v_detail, v_source),
        -- 効かせたルール番号（116 の選び方＋211 の下書きの言い回し）と、そのときの並び順の点数
        'applied_rules', nullif(
          coalesce(new.payload -> 'applied_rules', '[]'::jsonb) || coalesce(new.payload -> 'draft_rules', '[]'::jsonb),
          '[]'::jsonb
        ),
        'ai_score', new.payload -> 'slack_ma_digest' -> 'score',
        'priority', new.priority,
        'summary', left(coalesce(new.summary, ''), 500),
        'slack_ma_action', new.payload -> 'slack_ma_action',
        'slack_vr_action', new.payload -> 'slack_vr_action',
        'manual_reply', new.payload -> 'manual_reply',
        'loopware_action', new.payload -> 'loopware_action'
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
