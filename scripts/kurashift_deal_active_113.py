#!/usr/bin/env python3
"""113 物件買進め確認係 — 実装①: KURASHIFT → Slack #deal-active の書き込み。

正本は KURASHIFT（kurashift_re_deals）。#deal-active はその写し。
flow: docs/AIエージェントチーム/100_連絡・物件動向把握室/113_物件買進め確認係/flow.md

この実装①でやること（flow のステップ 1〜5）:
  1. 対象を読む: offer / loan、内見依頼中以降の viewing、summary_json.pursue のフォロー中、既にスレッドがある案件
     （step 無し・内見候補の viewing は物件メール照合の自動昇格なので写さない。2026-11-09 ドライランで 1000 件超）
  2. 「最後に動いた日」= deal_events / 台帳 comm_items（comm_links target_type=deal）/ updated_at の最新
  3. 未掲載 → 親メッセージを投稿し、ts を summary_json.slack_deal_active に保存
  4. 段階が変わった → 親メッセージを書き換え、スレッドに経緯を1行
  5. 内見日が明日 → スレッドに内見チェックリスト（1案件1回）

やらないこと: 仲介・銀行への送信、削除、KURASHIFT status の変更。
「どうしますか？」カード・ボタン・休眠・削除は実装②③で足す。

既定はドライラン（Slack に投稿せず、DB も書かない）。--apply で実行。

実行:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/kurashift_deal_active_113.py            # ドライラン
  python scripts/kurashift_deal_active_113.py --apply    # 投稿・保存
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

JST = dt.timezone(dt.timedelta(hours=9))
DEAL_ACTIVE_CHANNEL = "C0CAJQT7QQY"
DEALS_UI = "https://jarvis-trade-desk.vercel.app/realestate/deals"
AGENT_USERNAME = "113 物件買進め確認係"
SJ_KEY = "slack_deal_active"
CHECK_INTERVAL_DAYS = 14
TARGET_STATUSES = ("viewing", "offer", "loan")

STATUS_LABEL = {
    "info": "情報",
    "viewing": "内見",
    "offer": "買付",
    "loan": "融資",
    "purchased": "購入済",
    "passed": "見送り",
}
VIEWING_STEP_LABEL = {
    "candidate": "内見候補",
    "requested": "内見依頼中",
    "scheduled": "内見日確定",
    "done": "内見済",
}
ACQ_STAGE_LABEL = {
    "offer_prep": "買付準備",
    "offer_submitted": "買付提出",
    "offer_accepted": "買付通過",
    "loan_applied": "融資申込",
    "loan_approved": "融資承認",
    "contract": "売買契約",
    "settlement": "決済",
    "handover": "引渡し",
}
# 段階ごとの「次の一手」（ルール文。AI は使わない）
NEXT_STEP = {
    "pursue": "内見するか決める（内見候補に進めるなら KURASHIFT で）",
    "candidate": "仲介へ内見希望を連絡する（送信は本人）",
    "requested": "内見日時の確定を待つ／催促する",
    "scheduled": "内見の準備（持ち物・S3 ヒアリング項目）",
    "done": "内見メモを残し、買付へ進むか決める",
    "offer_prep": "指値の根拠を整理し、S6 に材料を渡す",
    "offer_submitted": "売主の回答を待つ",
    "offer_accepted": "融資用資料を依頼し、S7 に打診材料を渡す",
    "loan_applied": "融資審査の結果を待つ（融資特約の期限に注意）",
    "loan_approved": "売買契約の日程を決める",
    "contract": "決済の準備（残代金・登記）",
    "settlement": "引渡しの準備",
    "handover": "引渡し完了を確認し、KURASHIFT で購入済にする",
}
VIEWING_CHECKLIST = [
    "持ち物（メジャー・ライト・水平器・カメラ）",
    "建物: 雨漏り・傾き・シロアリ・設備年式",
    "周辺: 騒音・日当たり・駐車場・嫌悪施設",
    "S3 ヒアリング項目（KURASHIFT の回答欄に当日メモ）",
    "修繕の概算（S4 業者）を取る／依頼する",
]


# ------------------------------------------------------------------ 判定（純関数）


def sj_of(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return sj if isinstance(sj, dict) else {}


def is_pursued(deal: dict[str, Any]) -> bool:
    """apps/trade-desk/lib/reDealPursue.ts の明示フォロー判定に合わせる。"""
    sj = sj_of(deal)
    if sj.get("pursue_exclude") is True:
        return False
    if sj.get("pursue") is True:
        return True
    return isinstance(sj.get("pursue_at"), str) and bool(sj.get("pursue_at"))


# 松野さんが自分で進めた印のある内見段階。step 無し / candidate は物件メール照合が
# match_score で自動昇格させたもの（2026-11-09 時点で 1000 件超）なので写さない。
VIEWING_MOVED_STEPS = ("requested", "scheduled", "done")


def is_mirrored(deal: dict[str, Any]) -> bool:
    """既に #deal-active にスレッドがあり、まだ閉じていない。"""
    st = sj_of(deal).get(SJ_KEY)
    return isinstance(st, dict) and bool(st.get("ts")) and st.get("state") != "closed"


def is_target(deal: dict[str, Any]) -> bool:
    status = str(deal.get("status") or "")
    if status in ("passed", "purchased"):
        return False
    if status in ("offer", "loan"):
        return True
    if is_pursued(deal) or is_mirrored(deal):
        return True
    if status == "viewing":
        v = sj_of(deal).get("viewing")
        v = v if isinstance(v, dict) else {}
        return v.get("step") in VIEWING_MOVED_STEPS or bool(v.get("verdict"))
    return False


def stage_key(deal: dict[str, Any]) -> str:
    """段階の比較キー。親メッセージの書き換え判定に使う。"""
    status = str(deal.get("status") or "")
    sj = sj_of(deal)
    if status in ("offer", "loan"):
        acq = sj.get("acquisition") if isinstance(sj.get("acquisition"), dict) else {}
        return f"{status}:{acq.get('stage') or ''}"
    if status == "viewing":
        v = sj.get("viewing") if isinstance(sj.get("viewing"), dict) else {}
        return f"viewing:{v.get('step') or 'candidate'}"
    return "info:pursue"


def stage_label(deal: dict[str, Any]) -> str:
    key = stage_key(deal)
    status, _, sub = key.partition(":")
    if status == "viewing":
        return VIEWING_STEP_LABEL.get(sub, "内見候補")
    if status in ("offer", "loan"):
        return ACQ_STAGE_LABEL.get(sub) or STATUS_LABEL[status]
    return "フォロー中"


def next_step(deal: dict[str, Any]) -> str:
    _, _, sub = stage_key(deal).partition(":")
    return NEXT_STEP.get(sub) or NEXT_STEP.get("pursue", "")


def viewing_date(deal: dict[str, Any]) -> str | None:
    v = sj_of(deal).get("viewing")
    if isinstance(v, dict) and v.get("date"):
        return str(v["date"])[:10]
    return None


def deadline_text(deal: dict[str, Any]) -> str:
    vd = viewing_date(deal)
    if vd and str(deal.get("status")) == "viewing":
        t = (sj_of(deal).get("viewing") or {}).get("time")
        return f"内見 {vd}{' ' + str(t) if t else ''}"
    return "—"


def parse_ts(s: Any) -> dt.datetime | None:
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        try:
            d = dt.datetime.fromisoformat(str(s)[:10])
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=JST)
    return d


def last_moved_at(
    deal: dict[str, Any], event_times: list[Any], comm_times: list[Any]
) -> dt.datetime | None:
    cands = [parse_ts(x) for x in [deal.get("updated_at"), *event_times, *comm_times]]
    cands = [c for c in cands if c]
    return max(cands) if cands else None


def deal_url(deal_id: str) -> str:
    return f"{DEALS_UI}?deal={deal_id}"


def title_line(deal: dict[str, Any]) -> str:
    title = str(deal.get("title") or "（無題）")[:60]
    bits = []
    if deal.get("area"):
        bits.append(str(deal["area"])[:20])
    if deal.get("price_man") not in (None, ""):
        bits.append(f"{deal['price_man']}万")
    if deal.get("yield_pct") not in (None, ""):
        bits.append(f"{deal['yield_pct']}%")
    return f"{title}（{' / '.join(bits)}）" if bits else title


def build_parent(deal: dict[str, Any]) -> dict[str, Any]:
    """親メッセージ: タイトル＋4行（段階・次の一手・期限・KURASHIFT リンク）。"""
    url = deal_url(str(deal["id"]))
    lines = [
        f"*{title_line(deal)}*",
        f"段階: {stage_label(deal)}",
        f"次の一手: {next_step(deal)}",
        f"期限: {deadline_text(deal)}",
        f"<{url}|KURASHIFT で開く>",
    ]
    text = "\n".join(lines)
    return {
        "text": f"{title_line(deal)} — {stage_label(deal)}",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "113 物件買進め確認係 · 正本は KURASHIFT"}
                ],
            },
        ],
    }


def build_checklist(deal: dict[str, Any]) -> str:
    items = "\n".join(f"• {x}" for x in VIEWING_CHECKLIST)
    return f"明日は内見です（{deadline_text(deal)}）。\n{items}\n<{deal_url(str(deal['id']))}|KURASHIFT のチェックリスト>"


def plan_actions(
    deal: dict[str, Any], *, today: dt.date, moved: dt.datetime | None
) -> list[dict[str, Any]]:
    """1案件ぶんの動きを決める。副作用なし。"""
    sj = sj_of(deal)
    st = sj.get(SJ_KEY) if isinstance(sj.get(SJ_KEY), dict) else {}
    if st.get("state") == "closed":
        return []
    key = stage_key(deal)
    moved_day = moved.astimezone(JST).date().isoformat() if moved else today.isoformat()
    user_owned = st.get("posted_by") == "user"  # 手で立てたスレッド。Bot は親を書き換えられない
    acts: list[dict[str, Any]] = []
    if not st.get("ts"):
        acts.append({"kind": "post"})
    elif st.get("stage_key") != key:
        if not user_owned:
            acts.append({"kind": "update"})
        acts.append(
            {"kind": "reply", "text": f"{today.month}/{today.day} {stage_label(deal)}になりました"}
        )
    elif st.get("state") == "dormant" and st.get("last_moved_at") != moved_day:
        # 休眠中に動きがあった → 親を通常表示に戻す
        if not user_owned:
            acts.append({"kind": "update"})
        acts.append({"kind": "reply", "text": f"{today.month}/{today.day} 動きがあったので休眠を解きました"})
    elif should_go_dormant(st, today):
        acts.append({"kind": "dormant", "user_owned": user_owned})
    vd = viewing_date(deal)
    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    if (
        str(deal.get("status")) == "viewing"
        and vd == tomorrow
        and st.get("checklist_sent_for") != vd
    ):
        acts.append({"kind": "checklist", "date": vd})
    if not acts and st.get("last_moved_at") == moved_day:
        return []
    acts.append({"kind": "save", "stage_key": key, "last_moved_at": moved_day})
    return acts


DORMANT_ASKS = 2
DORMANT_IDLE_DAYS = 30
DELETE_AFTER_DAYS = 7


def should_go_dormant(st: dict[str, Any], today: dt.date) -> bool:
    """「どうしますか？」に2回答えがなく、30日動きがない。KURASHIFT の status は変えない。"""
    if st.get("state") not in ("needs_check",):
        return False
    if int(st.get("asked_count") or 0) < DORMANT_ASKS:
        return False
    try:
        moved = dt.date.fromisoformat(str(st.get("last_moved_at"))[:10])
    except ValueError:
        return False
    return (today - moved).days >= DORMANT_IDLE_DAYS


def build_parent_dormant(deal: dict[str, Any]) -> dict[str, Any]:
    url = deal_url(str(deal["id"]))
    text = f"💤 *{title_line(deal)}*　休眠（2回お聞きして返事がなく30日動きなし）\n<{url}|KURASHIFT で開く> · 動きがあれば自動で戻ります"
    return {"text": f"休眠: {title_line(deal)}", "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]}


def build_parent_closed(deal: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    reason = "見送り" if st.get("closed_reason") == "pass" else "完了"
    closed = str(st.get("closed_at") or "")
    try:
        gone = (dt.date.fromisoformat(closed) + dt.timedelta(days=DELETE_AFTER_DAYS)).isoformat()
    except ValueError:
        gone = "—"
    text = f"~{title_line(deal)}~\nクローズ（{reason}・{closed}）。{gone} にこのスレッドは消えます。KURASHIFT には残ります。"
    return {"text": f"クローズ: {title_line(deal)}", "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]}


def plan_closed(deal: dict[str, Any], today: dt.date) -> list[str]:
    """ボタンで閉じた案件: 表示を「クローズ」にし、7日後に消す。手で立てたスレッドは消さない。"""
    st = sj_of(deal).get(SJ_KEY)
    if not isinstance(st, dict) or st.get("state") != "closed" or not st.get("ts"):
        return []
    if st.get("deleted_at"):
        return []
    acts = []
    if not st.get("closed_shown"):
        acts.append("show_closed")
    try:
        due = dt.date.fromisoformat(str(st.get("closed_at"))[:10]) + dt.timedelta(days=DELETE_AFTER_DAYS)
    except ValueError:
        return acts
    if today >= due and st.get("posted_by") != "user":
        acts.append("delete")
    return acts


def next_state(
    st: dict[str, Any], acts: list[dict[str, Any]], *, ts: str | None, today: dt.date
) -> dict[str, Any]:
    new = dict(st)
    new.setdefault("channel", DEAL_ACTIVE_CHANNEL)
    new.setdefault("state", "active")
    new.setdefault("asked_count", 0)
    new.setdefault("closed_at", None)
    if ts:
        new["ts"] = ts
    for a in acts:
        if a["kind"] == "save":
            new["stage_key"] = a["stage_key"]
            if new.get("last_moved_at") != a["last_moved_at"]:
                new["last_moved_at"] = a["last_moved_at"]
                moved = dt.date.fromisoformat(a["last_moved_at"])
                cand = (moved + dt.timedelta(days=CHECK_INTERVAL_DAYS)).isoformat()
                # ボタンで延ばした日（続ける+14／保留+30）より手前には戻さない
                new["next_check_at"] = max(cand, str(new.get("next_check_at") or ""))
                if new.get("state") in ("needs_check", "dormant"):
                    new["state"] = "active"
        if a["kind"] == "checklist":
            new["checklist_sent_for"] = a["date"]
        if a["kind"] == "dormant":
            new["state"] = "dormant"
            new["dormant_at"] = today.isoformat()
    new["synced_at"] = today.isoformat()
    return new


# ------------------------------------------------------------------ 「どうしますか？」（実装②）

# 署名の秘密。apps/jarvis-dashboard/lib/dealActive113Core.ts の D113_SECRET_NAMES と同じ順。
ACTION_SECRET_NAMES = ("DEAL_ACTIVE_113_ACTION_TOKEN", "PROPERTY_GATE_ACTION_TOKEN")
ASK_ACTIONS = (
    ("continue", "続ける（あと14日）", "primary"),
    ("hold", "保留（30日後）", None),
    ("pass", "見送り", "danger"),
    ("done", "完了（外す）", None),
)
ASK_LIMIT = 15  # 1枚に載せる上限（Slack の blocks 50 個制限の内側）


def action_secret(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    for name in ACTION_SECRET_NAMES:
        v = (env.get(name) or "").strip()
        if v:
            return v
    return ""


def d113_sig(secret: str, action: str, deal_id: str) -> str:
    msg = f"d113:{action}:{deal_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:10]


def d113_value(secret: str, action: str, deal_id: str) -> str:
    return f"d113:{action}:{deal_id}:{d113_sig(secret, action, deal_id)}"


def is_due(deal: dict[str, Any], today: dt.date) -> bool:
    """聞く対象: スレッドがあり、閉じておらず、次に聞く日が今日以前。"""
    st = sj_of(deal).get(SJ_KEY)
    if not isinstance(st, dict) or not st.get("ts"):
        return False
    if st.get("state") in ("closed", "dormant"):
        return False
    nxt = str(st.get("next_check_at") or "")
    return bool(nxt) and nxt <= today.isoformat()


def idle_days(deal: dict[str, Any], today: dt.date) -> int | None:
    st = sj_of(deal).get(SJ_KEY) or {}
    try:
        return (today - dt.date.fromisoformat(str(st.get("last_moved_at"))[:10])).days
    except ValueError:
        return None


def build_ask_card(deals: list[dict[str, Any]], today: dt.date, secret: str) -> dict[str, Any]:
    head = f"*どうしますか？*　{today.month}/{today.day}（{len(deals)}件）\n14日以上動きのない案件です。1件ずつ選んでください。"
    blocks: list[dict[str, Any]] = [{"type": "section", "text": {"type": "mrkdwn", "text": head}}]
    for d in deals:
        did = str(d["id"])
        days = idle_days(d, today)
        st = sj_of(d).get(SJ_KEY) or {}
        note = []
        if days is not None:
            note.append(f"{days}日動きなし")
        if st.get("state") == "hold":
            note.append("保留の再確認")
        if int(st.get("asked_count") or 0) >= 1:
            note.append(f"{int(st['asked_count']) + 1}回目")
        line = f"*{title_line(d)}*\n{stage_label(d)} · {' · '.join(note) or '—'} · <{deal_url(did)}|KURASHIFT>"
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": line}})
        els = []
        for action, label, style in ASK_ACTIONS:
            b: dict[str, Any] = {
                "type": "button",
                "text": {"type": "plain_text", "text": label},
                "action_id": f"d113_{action}",
                "value": d113_value(secret, action, did),
            }
            if style:
                b["style"] = style
            els.append(b)
        blocks.append({"type": "actions", "block_id": f"d113_{did}", "elements": els})
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "見送りを押すと KURASHIFT も見送りになります · 113 物件買進め確認係"}],
        }
    )
    return {"text": f"どうしますか？（{len(deals)}件）", "blocks": blocks}


def asked_state(st: dict[str, Any], today: dt.date, card_ts: str | None) -> dict[str, Any]:
    new = dict(st)
    new["state"] = "needs_check"
    new["asked_count"] = int(st.get("asked_count") or 0) + 1
    new["last_asked_at"] = today.isoformat()
    # 返事がなければ翌週また聞く
    new["next_check_at"] = (today + dt.timedelta(days=7)).isoformat()
    if card_ts:
        new["ask_card_ts"] = card_ts
    return new


def run_ask(sb: Any, slack: "Slack", *, today: dt.date, apply: bool, secret: str) -> dict[str, int]:
    due = [d for d in fetch_deals(sb) if is_due(d, today)]
    due.sort(key=lambda d: str((sj_of(d).get(SJ_KEY) or {}).get("last_moved_at") or ""))
    due = due[:ASK_LIMIT]
    counts = {"asked": len(due), "error": 0}
    if not due:
        return counts
    try:
        ts = slack.post(build_ask_card(due, today, secret))
    except Exception as e:
        print(f"❌ ask card: {e}", file=sys.stderr)
        counts["error"] += 1
        return counts
    for d in due:
        new = asked_state(dict(sj_of(d).get(SJ_KEY) or {}), today, None if ts == "dry-run" else ts)
        if apply:
            save_state(sb, d, new)
        else:
            print(f"# dry-run ask-save {d['id']}: {json.dumps(new, ensure_ascii=False)}")
    return counts


# ------------------------------------------------------------------ I/O


class Slack:
    def __init__(self, token: str, channel: str, *, dry_run: bool) -> None:
        self.token = token
        self.channel = channel
        self.dry_run = dry_run

    def _call(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        body = {"channel": self.channel, "username": AGENT_USERNAME, **body}
        if self.dry_run:
            print(f"# dry-run {method}")
            print(json.dumps(body, ensure_ascii=False, indent=2)[:3000])
            return {"ok": True, "ts": "dry-run"}
        req = urllib.request.Request(
            f"https://slack.com/api/{method}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                j = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Slack HTTP {e.code}") from e
        if not j.get("ok"):
            raise RuntimeError(f"Slack {method}: {j.get('error')}")
        return j

    def post(self, payload: dict[str, Any], thread_ts: str | None = None) -> str:
        body = dict(payload)
        if thread_ts:
            body["thread_ts"] = thread_ts
        return str(self._call("chat.postMessage", body).get("ts") or "")

    def update(self, ts: str, payload: dict[str, Any]) -> None:
        self._call("chat.update", {"ts": ts, **payload})

    def delete(self, ts: str) -> None:
        body = {"ts": ts}
        if self.dry_run:
            print(f"# dry-run chat.delete ts={ts}")
            return
        self._call("chat.delete", body)

    def replies(self, ts: str) -> list[dict[str, Any]]:
        """スレッド内の返信（Bot 自身のものだけ消すために使う）。"""
        if self.dry_run:
            return []
        url = f"https://slack.com/api/conversations.replies?channel={self.channel}&ts={ts}&limit=200"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
        return [m for m in (j.get("messages") or []) if m.get("ts") != ts] if j.get("ok") else []


PAGE = 1000  # PostgREST の1回の上限


def _fetch_status(sb: Any, statuses: list[str]) -> list[dict[str, Any]]:
    cols = "id, title, status, area, price_man, yield_pct, updated_at, created_at, summary_json"
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = (
            sb.table("kurashift_re_deals").select(cols).in_("status", statuses)
            .order("id").range(start, start + PAGE - 1).execute().data
            or []
        )
        rows += page
        if len(page) < PAGE:
            return rows
        start += PAGE


def fetch_candidates(sb: Any) -> list[dict[str, Any]]:
    """内見段階以降（自動昇格を含む）と、フォロー中の info。手作業スレッドの紐付けに使う。"""
    rows = _fetch_status(sb, list(TARGET_STATUSES))
    rows += [d for d in _fetch_status(sb, ["info"]) if is_pursued(d) or is_mirrored(d)]
    return rows


def fetch_deals(sb: Any) -> list[dict[str, Any]]:
    rows = fetch_candidates(sb)
    out = [d for d in rows if is_target(d)]
    skipped = sum(1 for d in rows if str(d.get("status")) == "viewing" and not is_target(d))
    print(f"113 targets: {len(out)}（自動の内見候補 {skipped} 件は対象外）")
    return out


def fetch_event_times(sb: Any, deal_id: str) -> list[str]:
    try:
        r = (
            sb.table("kurashift_re_deal_events")
            .select("occurred_at")
            .eq("deal_id", deal_id)
            .order("occurred_at", desc=True)
            .limit(1)
            .execute()
        )
        return [x["occurred_at"] for x in (r.data or [])]
    except Exception:
        return []


def fetch_comm_times(sb: Any, deal_id: str) -> list[str]:
    """台帳（comm_links target_type=deal）の最新のやり取り。表が無くても止めない。"""
    try:
        links = (
            sb.table("comm_links")
            .select("item_id")
            .eq("target_type", "deal")
            .eq("target_id", deal_id)
            .execute()
            .data
            or []
        )
        ids = [x["item_id"] for x in links][:50]
        if not ids:
            return []
        r = (
            sb.table("comm_items")
            .select("occurred_at")
            .in_("id", ids)
            .order("occurred_at", desc=True)
            .limit(1)
            .execute()
        )
        return [x["occurred_at"] for x in (r.data or [])]
    except Exception:
        return []


def save_state(sb: Any, deal: dict[str, Any], state: dict[str, Any]) -> None:
    sj = dict(sj_of(deal))
    sj[SJ_KEY] = state
    # updated_at は触らない（「動いた日」を 113 自身の書き込みで更新しないため）
    sb.table("kurashift_re_deals").update({"summary_json": sj}).eq("id", deal["id"]).execute()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def run(
    sb: Any,
    slack: Slack,
    *,
    today: dt.date,
    apply: bool,
    only: str | None,
    max_posts: int = 10,
) -> dict[str, int]:
    counts = {"target": 0, "posted": 0, "updated": 0, "checklist": 0, "saved": 0, "deferred": 0, "dormant": 0, "missing": 0, "error": 0}
    for deal in fetch_deals(sb):
        if only and str(deal["id"]) != only:
            continue
        counts["target"] += 1
        did = str(deal["id"])
        moved = last_moved_at(deal, fetch_event_times(sb, did), fetch_comm_times(sb, did))
        acts = plan_actions(deal, today=today, moved=moved)
        if not acts:
            continue
        if any(a["kind"] == "post" for a in acts) and counts["posted"] >= max_posts:
            counts["deferred"] += 1  # 新規掲載は1回あたり上限まで。残りは次回
            continue
        st = dict(sj_of(deal).get(SJ_KEY) or {})
        ts = st.get("ts")
        try:
            for a in acts:
                k = a["kind"]
                if k == "post":
                    ts = slack.post(build_parent(deal))
                    counts["posted"] += 1
                elif k == "update":
                    slack.update(str(ts), build_parent(deal))
                    counts["updated"] += 1
                elif k == "reply":
                    slack.post({"text": a["text"]}, thread_ts=str(ts))
                elif k == "checklist":
                    slack.post({"text": build_checklist(deal)}, thread_ts=str(ts))
                    counts["checklist"] += 1
                elif k == "dormant":
                    if a.get("user_owned"):
                        slack.post({"text": "💤 休眠にしました（2回お聞きして返事がなく30日動きなし）。動きがあれば戻ります。"}, thread_ts=str(ts))
                    else:
                        slack.update(str(ts), build_parent_dormant(deal))
                    counts["dormant"] = counts.get("dormant", 0) + 1
            new = next_state(st, acts, ts=None if ts == "dry-run" else ts, today=today)
            if apply:
                save_state(sb, deal, new)
            else:
                print(f"# dry-run save {did}: {json.dumps(new, ensure_ascii=False)}")
            counts["saved"] += 1
        except Exception as e:  # 1件の失敗で全体を止めない
            if "message_not_found" in str(e):
                # Slack で手で消された。KURASHIFT は変えず、聞くだけ（#consult は実装④で）
                counts["missing"] = counts.get("missing", 0) + 1
                if apply:
                    save_state(sb, deal, {**st, "state": "missing", "missing_at": today.isoformat()})
                print(f"⚠️ {did}: 親メッセージが消されています（KURASHIFT も見送りにするかは松野さん判断）")
                continue
            counts["error"] += 1
            print(f"❌ {did}: {e}", file=sys.stderr)
    return counts


def fetch_closed(sb: Any) -> list[dict[str, Any]]:
    cols = "id, title, status, area, price_man, yield_pct, updated_at, summary_json"
    return (
        sb.table("kurashift_re_deals")
        .select(cols)
        .filter("summary_json->slack_deal_active->>state", "eq", "closed")
        .execute()
        .data
        or []
    )


def run_closed(sb: Any, slack: "Slack", *, today: dt.date, apply: bool) -> dict[str, int]:
    counts = {"closed_shown": 0, "deleted": 0, "error": 0}
    for deal in fetch_closed(sb):
        st = dict(sj_of(deal).get(SJ_KEY) or {})
        acts = plan_closed(deal, today)
        if not acts:
            continue
        ts = str(st["ts"])
        try:
            for k in acts:
                if k == "show_closed":
                    if st.get("posted_by") == "user":
                        slack.post({"text": build_parent_closed(deal, st)["text"]}, thread_ts=ts)
                    else:
                        slack.update(ts, build_parent_closed(deal, st))
                    st["closed_shown"] = True
                    counts["closed_shown"] += 1
                elif k == "delete":
                    for r in slack.replies(ts):
                        if r.get("bot_id"):
                            try:
                                slack.delete(str(r["ts"]))
                            except Exception:
                                pass  # 人の返信は Bot では消せない（残る）
                    slack.delete(ts)
                    st["deleted_at"] = today.isoformat()
                    counts["deleted"] += 1
            if apply:
                save_state(sb, deal, st)
            else:
                print(f"# dry-run closed-save {deal['id']}: {json.dumps(st, ensure_ascii=False)}")
        except Exception as e:
            counts["error"] += 1
            print(f"❌ closed {deal['id']}: {e}", file=sys.stderr)
    return counts


# ------------------------------------------------------------------ 手で立てたスレッドの紐付け

MANUAL_LINKS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "deal_active_113_manual.yaml"
)


def match_manual(entry: dict[str, Any], deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = [str(k) for k in (entry.get("match") or []) if str(k).strip()]
    if not keys:
        return []
    out = []
    for d in deals:
        blob = f"{d.get('title') or ''} {d.get('area') or ''}"
        if all(k in blob for k in keys):
            out.append(d)
    return out


def run_link_manual(sb: Any, *, today: dt.date, apply: bool, path: str = MANUAL_LINKS) -> dict[str, int]:
    """config の手作業スレッドを KURASHIFT の案件に結びつける。1件に決まったものだけ。"""
    import yaml  # noqa: PLC0415

    with open(path, encoding="utf-8") as f:
        entries = (yaml.safe_load(f) or {}).get("threads") or []
    deals = fetch_candidates(sb)
    counts = {"linked": 0, "already": 0, "unmatched": 0, "ambiguous": 0}
    for e in entries:
        if e.get("skip"):
            continue
        hits = match_manual(e, deals)
        if len(hits) != 1:
            key = "unmatched" if not hits else "ambiguous"
            counts[key] += 1
            print(f"⚠️ {e.get('label')}: {key}（候補 {len(hits)} 件）")
            continue
        d = hits[0]
        st = sj_of(d).get(SJ_KEY) or {}
        if st.get("ts"):
            counts["already"] += 1
            continue
        new = {
            "channel": DEAL_ACTIVE_CHANNEL,
            "ts": str(e["ts"]),
            "posted_by": "user",
            "state": "active",
            "stage_key": stage_key(d),
            "last_moved_at": str(e.get("posted_at") or today.isoformat()),
            "next_check_at": today.isoformat(),  # 次の「どうしますか？」に載せる
            "asked_count": 0,
            "closed_at": None,
            "linked_at": today.isoformat(),
        }
        if apply:
            save_state(sb, d, new)
        else:
            print(f"# dry-run link {e.get('label')} -> {d['id']}: {json.dumps(new, ensure_ascii=False)}")
        counts["linked"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="Slack に投稿し summary_json に保存する")
    ap.add_argument("--deal-id", help="1案件だけ処理する（試し用）")
    ap.add_argument("--max-posts", type=int, default=10, help="1回で新しく立てるスレッドの上限")
    ap.add_argument(
        "--ask",
        choices=("auto", "always", "never"),
        default="auto",
        help="「どうしますか？」カード: auto=月曜のみ / always / never",
    )
    ap.add_argument("--link-manual", action="store_true", help="config の手作業スレッドを案件に結びつけてから同期する")
    ap.add_argument("--today", help="基準日 YYYY-MM-DD（試し用）")
    args = ap.parse_args(argv)

    token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    if args.apply and not token:
        print("❌ --apply には SLACK_BOT_TOKEN が必要です", file=sys.stderr)
        return 2
    channel = (os.environ.get("DEAL_ACTIVE_CHANNEL") or DEAL_ACTIVE_CHANNEL).strip()
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(JST).date()

    if args.link_manual:
        lc = run_link_manual(sb_client(), today=today, apply=args.apply)
        print("113 link-manual: " + " ".join(f"{k}={v}" for k, v in lc.items()))

    counts = run(
        sb_client(),
        Slack(token, channel, dry_run=not args.apply),
        today=today,
        apply=args.apply,
        only=args.deal_id,
        max_posts=args.max_posts,
    )
    mode = "apply" if args.apply else "dry-run"
    print(f"113 deal-active {mode} {today}: " + " ".join(f"{k}={v}" for k, v in counts.items()))
    err = counts["error"]
    cc = run_closed(sb_client(), Slack(token, channel, dry_run=not args.apply), today=today, apply=args.apply)
    print("113 closed: " + " ".join(f"{k}={v}" for k, v in cc.items()))
    err += cc["error"]
    if args.ask == "always" or (args.ask == "auto" and today.weekday() == 0):
        secret = action_secret() or ("dry-run-secret" if not args.apply else "")
        if not secret:
            print("❌ カードのボタン署名に DEAL_ACTIVE_113_ACTION_TOKEN か PROPERTY_GATE_ACTION_TOKEN が必要です", file=sys.stderr)
            return 2
        ac = run_ask(
            sb_client(), Slack(token, channel, dry_run=not args.apply), today=today, apply=args.apply, secret=secret
        )
        print(f"113 ask {mode}: asked={ac['asked']} error={ac['error']}")
        err += ac["error"]
    return 1 if err else 0


if __name__ == "__main__":
    raise SystemExit(main())
