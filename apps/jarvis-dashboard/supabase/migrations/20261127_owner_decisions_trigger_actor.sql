-- 判断ログ（owner_decisions）— 押した人のアカウントを写す（2026-11-27 松野さん決定）
-- 目的: ボット用アカウントの操作と松野さん本人の判断を、判断ログで区別できるようにする。
--   - payload.actor_id: triage_items.payload.actor_id（ダッシュボードのサーバーアクションが書く
--     Supabase ユーザーID。メールアドレスは入れない）を写す。無ければ入らない（従来どおり）。
-- 変更は 20261127_owner_decisions_partner_key.sql の関数の置き換えで、actor_id の1行だけ足す。表・トリガー・権限は変えない。過去分は埋めない。
-- 戻すとき: 20261127_owner_decisions_partner_key.sql の関数部分を再実行（actor_id が付かなくなるだけ）。

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
  v_key text;
begin
  -- 双子（同じメールの別 id）へ写しただけの変化は判断ログに入れない（20261109_triage_items_twins）
  if (new.payload ->> 'twin_synced_from') is distinct from (old.payload ->> 'twin_synced_from') then
    return new;
  end if;
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
      v_source := coalesce(new.payload -> 'loopware_action' ->> 'source', 'loopware');
    end if;

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

    -- 送り手の識別子: 「名前 <addr>」でも素のアドレスでも小文字のアドレスに。無ければ partner 名
    v_key := lower(nullif(btrim(coalesce(
      substring(new.from_email from '<([^<>@ ]+@[^<>@ ]+)>'),
      case when new.from_email ~ '^[^<>@ ]+@[^<>@ ]+$' then new.from_email end,
      new.partner
    )), ''));

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
        'partner_key', v_key,
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
        'loopware_action', new.payload -> 'loopware_action',
        'actor_id', new.payload -> 'actor_id'
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
-- トリガー本体（after update of status）は 20261107 のまま。関数の置き換えだけで効く。
