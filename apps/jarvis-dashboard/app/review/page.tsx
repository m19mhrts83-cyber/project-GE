import Shell from "@/components/Shell";
import ReviewCandidateActions from "@/components/ReviewCandidateActions";
import { createServiceClient } from "@/lib/supabase/admin";
import { loopwareHref } from "@/lib/loopwareLink";
import {
  MAIL_SURFACES,
  byEmployee,
  candidateStates,
  delta,
  isStale,
  parseCandidates,
  pct,
  rate,
  reasonCounts,
  ruleEffects,
  stats,
  troubles,
  EMPLOYEE_LABEL,
  type DecisionLite,
} from "@/lib/weeklyReview";

export const dynamic = "force-dynamic";
export const metadata = { title: "週次レビュー｜Jarvis" };

const DAY = 86400_000;
const COLS = "id,decided_at,surface,action,source,employee,lane,partner,subject,ai_proposal,final_text,edited,note,payload";

const REASON_LABEL: Record<string, string> = {
  no_reply: "回答不要",
  promo: "宣伝",
  not_important: "大事でない",
  self_or_grok: "自分・Grok",
  hesitate: "迷った",
  no_time: "時間がない",
  unsure: "迷った",
  need_info: "情報が足りない",
  waiting: "返事待ち",
};

const ACTION_LABEL: Record<string, string> = {
  sent: "送った",
  skipped: "見送り",
  snoozed: "後で",
  done: "対応済み",
  hesitated: "迷った",
  unseen: "未判断",
  wrong: "見落とし",
  meh: "いまいち",
  todo: "ToDo",
};

function md(iso: string): string {
  const d = new Date(Date.parse(iso) + 9 * 3600_000);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

async function load() {
  const sb = createServiceClient();
  if (!sb) return null;
  const now = Date.now();
  const since = new Date(now - 7 * DAY).toISOString();
  const prevSince = new Date(now - 14 * DAY).toISOString();
  const [mail, reviews, meta] = await Promise.all([
    sb
      .from("owner_decisions")
      .select(COLS)
      .in("surface", [...MAIL_SURFACES])
      .gte("decided_at", prevSince)
      .order("decided_at", { ascending: false })
      .limit(3000),
    sb
      .from("owner_decisions")
      .select("id,decided_at,surface,action,note,payload")
      .eq("surface", "rule_review")
      .gte("decided_at", new Date(now - 60 * DAY).toISOString())
      .order("decided_at", { ascending: false })
      .limit(300),
    sb.from("sync_meta").select("value,updated_at").eq("key", "loopware_rule_candidates").maybeSingle(),
  ]);
  const rows = (mail.data || []) as DecisionLite[];
  const cur = rows.filter((r) => r.decided_at >= since);
  const prev = rows.filter((r) => r.decided_at < since);
  const cand = parseCandidates(meta.data?.value);

  const evIds = [
    ...new Set(cand.candidates.flatMap((c) => (c.evidence || []).map((x) => Number(x)).filter((x) => Number.isFinite(x) && x > 0))),
  ].slice(0, 200);
  const ev = evIds.length
    ? await sb.from("owner_decisions").select("id,decided_at,action,subject,partner,note").in("id", evIds)
    : { data: [] as Record<string, unknown>[] };
  const evidence = new Map<string, Record<string, unknown>>();
  for (const e of ev.data || []) evidence.set(String(e.id), e);

  return {
    since,
    error: mail.error?.message || null,
    cur,
    prev,
    cand,
    states: candidateStates((reviews.data || []) as DecisionLite[]),
    evidence,
    reviewsThisWeek: ((reviews.data || []) as DecisionLite[]).filter((r) => r.decided_at >= since),
  };
}

export default async function ReviewPage() {
  const d = await load();
  if (!d) {
    return (
      <Shell active="/review">
        <h1>週次レビュー</h1>
        <p className="empty">Supabase が未設定のため読めません。</p>
      </Shell>
    );
  }
  const s = stats(d.cur);
  const p = stats(d.prev);
  const emps = byEmployee(d.cur, d.prev);
  const reasons = reasonCounts(d.cur);
  const trouble = troubles(d.cur);
  const effects = ruleEffects(d.cur);
  const pending = d.cand.candidates.filter((c) => !d.states.get(c.id)?.decided);
  const judged = d.cand.candidates.filter((c) => d.states.get(c.id)?.decided);
  const stale = isStale(d.cand.at);
  const changes = d.reviewsThisWeek.filter((r) => ["rule_accept", "rule_revert"].includes(r.action));

  return (
    <Shell active="/review">
      <h1>週次レビュー</h1>
      <p className="sub">
        メール・Slack の判断（直近7日 {md(d.since)}〜）。AI の見立て（ルール候補）を確かめて、採用したものだけルール帳に入ります。
        押した判断も判断ログに残り、来週の見立てに使われます。
      </p>
      {d.error ? <p className="empty">判断ログの読み込みに失敗: {d.error}</p> : null}

      <h2 style={{ marginTop: 24 }}>1. 確認待ちのフィードバック（{pending.length} 件）</h2>
      <p className="sub">
        土曜の週次分析が判断ログから作った候補です
        {d.cand.week ? `（${d.cand.week}${d.cand.at ? `・${md(d.cand.at)} 作成` : ""}）` : ""}。
        「採用する」でルール帳へ、「違う」は8週間出しません。言いたいことがあれば「直してひとこと」。
      </p>
      {stale ? (
        <p className="empty">
          週次分析の結果が8日以上新しくなっていません。土曜の分析（jarvis_loopware_weekly.py --publish）が止まっていないか確認が要ります。
        </p>
      ) : null}
      {pending.length === 0 ? <p className="empty">確認待ちはありません。</p> : null}
      {[...pending, ...judged].map((c) => {
        const st = d.states.get(c.id);
        return (
          <article key={c.id} className="card" style={{ marginBottom: 12 }}>
            <header>
              <span className="lvl">{c.status === "hypothesis" ? "仮説" : "候補"}</span>
              <strong>{c.text}</strong>
            </header>
            <p className="sub" style={{ margin: "6px 0" }}>
              {EMPLOYEE_LABEL[c.employee] || c.employee}・根拠: {c.why}
              {c.needs_ai ? "・文言は 314 が差分から埋めます" : ""}
            </p>
            {c.rule_line ? (
              <p className="sub" style={{ margin: "4px 0", fontFamily: "monospace", fontSize: 12 }}>
                {c.rule_line}
              </p>
            ) : null}
            {(c.evidence || []).length ? (
              <details>
                <summary className="sub">根拠になった判断（{c.evidence.length} 件）</summary>
                <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                  {c.evidence.slice(0, 10).map((id) => {
                    const e = d.evidence.get(String(id));
                    return (
                      <li key={String(id)} className="sub">
                        {e
                          ? `${md(String(e.decided_at))} ${ACTION_LABEL[String(e.action)] || e.action}｜${String(e.partner || "")} ${String(e.subject || "").slice(0, 60)}${e.note ? `（${String(e.note).slice(0, 60)}）` : ""}`
                          : `#${id}`}
                      </li>
                    );
                  })}
                </ul>
              </details>
            ) : null}
            {st?.comments.length ? (
              <p className="sub" style={{ margin: "6px 0 0" }}>
                これまでのひとこと: {st.comments.slice(-3).join(" ／ ")}
              </p>
            ) : null}
            <ReviewCandidateActions candidate={c} decided={st?.decided || null} />
          </article>
        );
      })}

      <h2 style={{ marginTop: 28 }}>2. 今週の数字（前週比）</h2>
      <div className="stats">
        <div className="stat">
          判断 <strong>{s.total}</strong> <small>{delta(s.total, p.total)}</small>
        </div>
        <div className="stat">
          採った <strong>{s.take}</strong> <small>{delta(s.take, p.take)}</small>
        </div>
        <div className="stat">
          見送った <strong>{s.ng}</strong> <small>{delta(s.ng, p.ng)}</small>
        </div>
        <div className="stat">
          迷った・未判断 <strong>{s.hesitate + s.none}</strong> <small>{delta(s.hesitate + s.none, p.hesitate + p.none)}</small>
        </div>
        <div className="stat">
          直して送った <strong>{pct(rate(s.edited, s.sent))}</strong>{" "}
          <small>
            {s.edited}/{s.sent}（前週 {pct(rate(p.edited, p.sent))}）
          </small>
        </div>
        <div className="stat">
          見落とし <strong>{s.misses}</strong> <small>{delta(s.misses, p.misses)}</small>
        </div>
      </div>
      {emps.length ? (
        <table className="prop-event-table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>社員</th>
              <th>判断</th>
              <th>見送り率</th>
              <th>直して送った率</th>
              <th>見落とし</th>
            </tr>
          </thead>
          <tbody>
            {emps.map((e) => (
              <tr key={e.employee}>
                <td>{e.label}</td>
                <td>
                  {e.now.total}（{delta(e.now.total, e.prev.total)}）
                </td>
                <td>
                  {pct(rate(e.now.ng, e.now.total))}（前週 {pct(rate(e.prev.ng, e.prev.total))}）
                </td>
                <td>
                  {pct(rate(e.now.edited, e.now.sent))}（前週 {pct(rate(e.prev.edited, e.prev.sent))}）
                </td>
                <td>{e.now.misses}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">この2週間、メール・Slack の判断ログがありません。</p>
      )}
      {reasons.length ? (
        <p className="sub" style={{ marginTop: 8 }}>
          見送り・迷った理由の多い順: {reasons.map((r) => `${REASON_LABEL[r.tag] || r.tag} ${r.n}`).join("・")}
        </p>
      ) : null}

      <h2 style={{ marginTop: 28 }}>3. 見ておきたい判断（{trouble.length} 件）</h2>
      <p className="sub">見落とし・大きく直して送った・送った後の「いまいち」。同じ形が2件以上たまると、土曜の分析で候補になります。</p>
      {trouble.length === 0 ? <p className="empty">今週はありません。</p> : null}
      {trouble.length ? (
        <table className="prop-event-table">
          <thead>
            <tr>
              <th>日</th>
              <th>種類</th>
              <th>社員</th>
              <th>件名・相手</th>
              <th>何があったか</th>
            </tr>
          </thead>
          <tbody>
            {trouble.map((t) => (
              <tr key={t.id}>
                <td>{md(t.at)}</td>
                <td>{t.kind}</td>
                <td>{EMPLOYEE_LABEL[t.employee] || t.employee}</td>
                <td>{t.subject.slice(0, 50)}</td>
                <td>{t.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      <h2 style={{ marginTop: 28 }}>4. 変わったこと・効いたルール</h2>
      <ul style={{ paddingLeft: 18 }}>
        {changes.length === 0 ? <li className="sub">今週採用・取り消したルールはありません。</li> : null}
        {changes.map((r) => {
          const pl = (r.payload || {}) as Record<string, unknown>;
          return (
            <li key={String(r.id)} className="sub">
              {md(r.decided_at)} {r.action === "rule_accept" ? "採用" : "取り消し"}: {String(pl.text || pl.rule_line || pl.rule_id || "")}
            </li>
          );
        })}
        {effects.map((e) => (
          <li key={e.rule} className="sub">
            {e.rule}: 効いた判断 {e.take + e.ng + e.other} 件（採った {e.take}・見送った {e.ng}）
          </li>
        ))}
      </ul>

      <p className="sub" style={{ marginTop: 24 }}>
        1件ずつの判断は{" "}
        <a href={loopwareHref("/desk", { from: "review" })} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", fontWeight: 600 }}>
          ループウェアの判断デスク ↗
        </a>
        、採用済みルールの取り消しは{" "}
        <a href={loopwareHref("/rules", { from: "review" })} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", fontWeight: 600 }}>
          ルール候補 ↗
        </a>
        で。
      </p>
    </Shell>
  );
}
