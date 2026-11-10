-- KURASHIFT のお金の判断 → 共有の判断ログ（owner_decisions）v2：答え合わせと判断メモの付帯情報
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
--
-- 20261110_kurashift_owner_decisions.sql の関数とトリガーを置き換える（中身は上位互換。
-- 20261110 が未適用でも、この1本だけ適用すればよい）。
-- 足したもの:
--   - 答え合わせ（S21 使った結果を振り返る）: 良かった=good／まあまあ=meh／やり直したい=wrong
--       資金移動: assist_payload.last_retro が変わったとき（status は変わらない）
--       物件: kurashift_re_deal_events に payload.action=retro の行が入ったとき
--     payload.retro_of に元の判断（資金=判断の時刻、物件=イベント id）を残す
--   - 判断メモの付帯情報: decide_ms（開いてから決めるまで）、suggested_tags（画面が出した候補）、
--     same_as_last（「前回と同じ」をそのまま使った）
-- 記録の失敗で本線は止めない。二重記録は payload.idem_key で防ぐ。
-- 契約: apps/loopware/lib/decisionContract.ts

-- ---------------------------------------------------------------- 資金移動
create or replace function public.kurashift_money_ops_log_owner_decision()
returns trigger language plpgsql
security definer
set search_path = public
as $$
declare
  v_action text;
  v_outcome text;
  v_ld jsonb;
  v_from_app boolean := false;
  v_tags jsonb := '[]'::jsonb;
  v_note text;
  v_scope text := 'once';
  v_key text;
begin
  -- 答え合わせ（status は変わらず last_retro だけが変わる）
  if new.status is not distinct from old.status then
    begin
      v_ld := new.assist_payload -> 'last_retro';
      if v_ld is not null
         and v_ld is distinct from (old.assist_payload -> 'last_retro')
         and v_ld ->> 'quality' in ('good', 'meh', 'regret') then
        v_key := 'kurashift:kurashift_money:' || new.id::text || ':retro:' || coalesce(v_ld ->> 'at', '');
        if not exists (select 1 from public.owner_decisions where payload ->> 'idem_key' = v_key) then
          insert into public.owner_decisions (
            surface, action, source, target_type, target_id, kind, subject, prev_status, note, payload
          ) values (
            'kurashift_money',
            case v_ld ->> 'quality' when 'good' then 'good' when 'meh' then 'meh' else 'wrong' end,
            'kurashift', 'money_op', new.id::text, new.kind, new.title, new.status,
            nullif(v_ld ->> 'note', ''),
            jsonb_strip_nulls(jsonb_build_object(
              'v', 1,
              'outcome', case v_ld ->> 'quality' when 'good' then 'take' when 'meh' then 'note' else 'ng' end,
              'idem_key', v_key,
              'source_detail', 'kurashift_retro',
              'quality', v_ld ->> 'quality',
              'retro_of', v_ld ->> 'ref_at',
              'amount_jpy', new.amount_jpy
            ))
          );
        end if;
      end if;
    exception when others then
      raise warning 'owner_decisions (kurashift_money retro) log skipped: %', sqlerrm;
    end;
    return new;
  end if;
  -- 実行中へ・草案に戻すは進み具合なので判断ログには入れない（アプリ側の decision_log には残る）
  v_action := case new.status
    when 'approved' then 'accept'
    when 'consulting' then 'hesitated'
    when 'cancelled' then 'reject'
    when 'done' then 'done'
  end;
  if v_action is null then
    return new;
  end if;

  begin
    v_ld := new.assist_payload -> 'last_decision';
    if v_ld is not null
       and v_ld ->> 'to' = new.status
       and (v_ld ->> 'at')::timestamptz > now() - interval '5 minutes' then
      v_from_app := true;
      v_tags := coalesce(v_ld -> 'reason_tags', '[]'::jsonb);
      v_note := nullif(v_ld ->> 'note', '');
      v_scope := coalesce(nullif(v_ld ->> 'scope', ''), 'once');
    end if;
    v_outcome := case v_action
      when 'accept' then 'take'
      when 'done' then 'take'
      when 'reject' then 'ng'
      when 'hesitated' then 'hesitate'
    end;

    v_key := 'kurashift:kurashift_money:' || new.id::text || ':' || new.status || ':'
      || case when v_from_app then v_ld ->> 'at' else to_char(now(), 'YYYYMMDDHH24MI') end;
    if exists (select 1 from public.owner_decisions where payload ->> 'idem_key' = v_key) then
      return new;
    end if;

    insert into public.owner_decisions (
      surface, action, source, target_type, target_id,
      kind, subject, prev_status, ai_proposal, note, payload
    ) values (
      'kurashift_money', v_action,
      case when v_from_app then 'kurashift' else 'script' end,
      'money_op', new.id::text,
      new.kind, new.title, old.status,
      nullif(left(coalesce(new.rationale, ''), 4000), ''),
      v_note,
      jsonb_strip_nulls(jsonb_build_object(
        'v', 1,
        'outcome', v_outcome,
        'idem_key', v_key,
        'source_detail', case when v_from_app then 'kurashift_money_ops' else 'money_ops_status' end,
        'reason_tags', nullif(v_tags, '[]'::jsonb),
        'scope', v_scope,
        'from_status', old.status,
        'to_status', new.status,
        'amount_jpy', new.amount_jpy,
        'from_account', new.from_account,
        'to_account', new.to_account,
        'due_date', new.assist_payload ->> 'due_date',
        'decided_by', case when v_from_app then v_ld ->> 'by' end,
        'decide_ms', case when v_from_app then v_ld -> 'decide_ms' end,
        'suggested_tags', case when v_from_app then nullif(v_ld -> 'suggested_tags', '[]'::jsonb) end,
        'same_as_last', case when v_from_app and (v_ld ->> 'same_as_last') = 'true' then true end
      ))
    );
  exception when others then
    raise warning 'owner_decisions (kurashift_money) log skipped: %', sqlerrm;
  end;
  return new;
end;
$$;

revoke all on function public.kurashift_money_ops_log_owner_decision() from public, anon, authenticated;

drop trigger if exists kurashift_money_ops_log_owner_decision on public.kurashift_money_ops;
create trigger kurashift_money_ops_log_owner_decision
  after update of status, assist_payload on public.kurashift_money_ops
  for each row execute function public.kurashift_money_ops_log_owner_decision();

-- ---------------------------------------------------------------- 物件
create or replace function public.kurashift_re_deal_events_log_owner_decision()
returns trigger language plpgsql
security definer
set search_path = public
as $$
declare
  v_deal_action text;
  v_action text;
  v_outcome text;
  v_title text;
  v_tags jsonb;
  v_key text;
begin
  if coalesce(new.actor, '') <> 'user'
     or new.event_type not in ('review_confirm', 'review_pass', 'status_change', 'note') then
    return new;
  end if;
  v_deal_action := new.payload ->> 'action';

  -- 答え合わせ
  if v_deal_action = 'retro' then
    begin
      if new.payload ->> 'quality' in ('good', 'meh', 'regret') then
        select title into v_title from public.kurashift_re_deals where id = new.deal_id;
        v_key := 'kurashift:kurashift_deal:event:' || new.id::text;
        if not exists (select 1 from public.owner_decisions where payload ->> 'idem_key' = v_key) then
          insert into public.owner_decisions (
            surface, action, source, target_type, target_id, kind, subject, note, payload
          ) values (
            'kurashift_deal',
            case new.payload ->> 'quality' when 'good' then 'good' when 'meh' then 'meh' else 'wrong' end,
            'kurashift', 're_deal', new.deal_id::text, 'retro', v_title,
            nullif(new.payload ->> 'note', ''),
            jsonb_strip_nulls(jsonb_build_object(
              'v', 1,
              'outcome', case new.payload ->> 'quality' when 'good' then 'take' when 'meh' then 'note' else 'ng' end,
              'idem_key', v_key,
              'source_detail', 'kurashift_retro',
              'quality', new.payload ->> 'quality',
              'retro_of', new.payload ->> 'ref_event_id',
              'deal_event_id', new.id
            ))
          );
        end if;
      end if;
    exception when others then
      raise warning 'owner_decisions (kurashift_deal retro) log skipped: %', sqlerrm;
    end;
    return new;
  end if;
  if new.event_type = 'note' then
    return new;
  end if;
  v_action := case v_deal_action
    when 'confirm' then 'accept'        -- 候補に残す（問合せへ）
    when 'pass' then 'skipped'          -- 見送り
    when 'pursue_add' then 'adopt'      -- 進行中に入れる
    when 'pursue_remove' then 'defer'   -- 進行中から外す（見送りではない）
    when 'set_viewing' then 'adopt'     -- 内見へ
    when 'set_offer' then 'adopt'       -- 買付へ
  end;
  if v_action is null then
    return new;
  end if;

  begin
    select title into v_title from public.kurashift_re_deals where id = new.deal_id;
    v_tags := coalesce(new.payload -> 'reason_tags', '[]'::jsonb);
    v_key := 'kurashift:kurashift_deal:event:' || new.id::text;
    if exists (select 1 from public.owner_decisions where payload ->> 'idem_key' = v_key) then
      return new;
    end if;
    v_outcome := case v_action
      when 'accept' then 'take'
      when 'adopt' then 'take'
      when 'skipped' then 'ng'
      when 'defer' then 'later'
    end;

    insert into public.owner_decisions (
      surface, action, source, target_type, target_id,
      kind, subject, prev_status, note, payload
    ) values (
      'kurashift_deal', v_action, 'kurashift', 're_deal', new.deal_id::text,
      v_deal_action, v_title, new.from_status,
      nullif(new.payload ->> 'note', ''),
      jsonb_strip_nulls(jsonb_build_object(
        'v', 1,
        'outcome', v_outcome,
        'idem_key', v_key,
        'source_detail', 'kurashift_re_deal_events',
        'reason_tags', nullif(v_tags, '[]'::jsonb),
        'scope', coalesce(nullif(new.payload ->> 'scope', ''), 'once'),
        'deal_action', v_deal_action,
        'from_status', new.from_status,
        'to_status', new.to_status,
        'deal_event_id', new.id,
        'decided_by', new.payload ->> 'decided_by',
        'decide_ms', new.payload -> 'decide_ms',
        'suggested_tags', nullif(new.payload -> 'suggested_tags', '[]'::jsonb),
        'same_as_last', case when (new.payload ->> 'same_as_last') = 'true' then true end
      ))
    );
  exception when others then
    raise warning 'owner_decisions (kurashift_deal) log skipped: %', sqlerrm;
  end;
  return new;
end;
$$;

revoke all on function public.kurashift_re_deal_events_log_owner_decision() from public, anon, authenticated;

drop trigger if exists kurashift_re_deal_events_log_owner_decision on public.kurashift_re_deal_events;
create trigger kurashift_re_deal_events_log_owner_decision
  after insert on public.kurashift_re_deal_events
  for each row execute function public.kurashift_re_deal_events_log_owner_decision();
