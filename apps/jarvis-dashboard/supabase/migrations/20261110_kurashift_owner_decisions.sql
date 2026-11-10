-- KURASHIFT のお金の判断を共有の判断ログ（owner_decisions）へ写す（ループウェア契約 v1）
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
--
-- これまで: KURASHIFT の資金移動（承認・相談・取消・完了）と物件の判断（見送り・内見・買付…）は
--   アプリの表にだけ残り、owner_decisions に1件も届いていなかった。週次レビュー（314・Nody /review）から見えない。
-- これから: triage と同じく DB トリガーで写す。アプリ・スクリプト・Slack のどこから変えても残る。
--   - 資金移動: kurashift_money_ops の status が変わったとき → surface=kurashift_money
--     理由は アプリが assist_payload.last_decision に置いたもの（reason_tags / note / scope）を使う
--   - 物件: kurashift_re_deal_events に actor=user の判断行が入ったとき → surface=kurashift_deal
--     理由は その行の payload（reason_tags / note / scope）
-- 記録の失敗で本線（status 更新・イベント追加）は止めない（exception → warning）。
-- 同じ判断の二重記録は payload.idem_key で1行にまとめる（先に同じ鍵があれば入れない。
--   20261108_owner_decisions_idem_key.sql の索引が未適用でも動く）。
-- 契約: apps/loopware/lib/decisionContract.ts（写し apps/trade-desk/lib/decisionContract.ts）

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
  if new.status is not distinct from old.status then
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
        'decided_by', case when v_from_app then v_ld ->> 'by' end
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
  after update of status on public.kurashift_money_ops
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
     or new.event_type not in ('review_confirm', 'review_pass', 'status_change') then
    return new;
  end if;
  v_deal_action := new.payload ->> 'action';
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
        'decided_by', new.payload ->> 'decided_by'
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
