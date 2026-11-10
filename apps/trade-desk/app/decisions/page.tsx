import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { fmtYen, formatJstDateTime } from "@/lib/format";
import {
  dealRows,
  moneyRows,
  sortNewest,
  summarize,
  type DecisionRow,
} from "@/lib/kurashiftDecisionLog";

export const dynamic = "force-dynamic";

const DAYS = 60;
const LOOPWARE_REVIEW_URL =
  (process.env.NEXT_PUBLIC_LOOPWARE_URL || "https://jarvis-loopware.vercel.app").replace(/\/$/, "") +
  "/review";

const OUTCOME_LABEL: Record<DecisionRow["outcome"], string> = {
  take: "進めた",
  ng: "見送った",
  hesitate: "迷った",
  later: "後で",
  note: "メモ",
};

function pct(n: number | null): string {
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

export default async function DecisionsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const since = new Date(Date.now() - DAYS * 86400_000).toISOString();

  const [{ data: ops }, { data: events }] = await Promise.all([
    supabase
      .from("kurashift_money_ops")
      .select("id, title, amount_jpy, assist_payload, updated_at")
      .gte("updated_at", since)
      .order("updated_at", { ascending: false })
      .limit(200),
    supabase
      .from("kurashift_re_deal_events")
      .select("id, deal_id, event_type, actor, occurred_at, payload")
      .eq("actor", "user")
      .in("event_type", ["review_confirm", "review_pass", "status_change"])
      .gte("occurred_at", since)
      .order("occurred_at", { ascending: false })
      .limit(400),
  ]);

  const dealIds = Array.from(new Set((events ?? []).map((e) => e.deal_id)));
  const titles = new Map<string, string>();
  if (dealIds.length) {
    const { data: deals } = await supabase
      .from("kurashift_re_deals")
      .select("id, title")
      .in("id", dealIds.slice(0, 400));
    for (const d of deals ?? []) titles.set(d.id, d.title || "");
  }

  const rows = sortNewest([
    ...moneyRows(ops ?? []).filter((r) => r.at >= since),
    ...dealRows(events ?? [], titles),
  ]);
  const money = summarize(rows.filter((r) => r.kind === "money"));
  const deal = summarize(rows.filter((r) => r.kind === "deal"));
  const all = summarize(rows);

  return (
    <Shell active="/decisions" email={user?.email ?? null}>
      <p className="page-kicker">ループウェア</p>
      <h1>お金の判断ログ</h1>
      <p className="sub">
        資金移動（承認・相談・取消・完了）と物件（見送り・内見・買付…）の判断を、直近{DAYS}日ぶん並べます。
        理由は任意。「次も同じに」が付いた判断は基準の候補で、ルールにするかは週1のレビューで決めます。
        同じ記録は共有の判断ログにも写り、Nody の週1レビューと 314 の週次から見えます。
      </p>

      <div className="grid" style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        {[
          { name: "資金移動", s: money },
          { name: "物件", s: deal },
        ].map(({ name, s }) => (
          <div className="card" key={name}>
            <header>
              <span className="lvl">{name}</span>
              <strong>{s.total}件</strong>
            </header>
            <p className="meta" style={{ marginTop: 6 }}>
              進めた {s.take} ／ 見送った {s.ng} ／ 迷った {s.hesitate} ／ 後で {s.later}
            </p>
            <p className="meta">理由が付いた割合 {pct(s.reasonRate)}</p>
          </div>
        ))}
        <div className="card">
          <header>
            <span className="lvl">週1のレビュー</span>
            <strong>基準を見直す</strong>
          </header>
          <p className="meta" style={{ marginTop: 6 }}>
            基準の候補 {all.ruleCandidates.length}件。採用は本人が決めたものだけ。
          </p>
          <p className="meta">
            <a href={LOOPWARE_REVIEW_URL} target="_blank" rel="noreferrer">
              Nody の週1レビューを開く
            </a>
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">共通パターン</span>
          <strong>同じ理由が2件以上</strong>
        </header>
        {all.patterns.length === 0 ? (
          <p className="meta" style={{ marginTop: 6 }}>
            まだありません（1件だけの理由は一般化しません）。
          </p>
        ) : (
          <ul className="meta" style={{ marginTop: 6 }}>
            {all.patterns.map((p) => (
              <li key={`${p.kind}:${p.outcome}:${p.tag}`}>
                {p.kind === "money" ? "資金移動" : "物件"}・{OUTCOME_LABEL[p.outcome]}：「{p.label}」{p.count}件
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">一覧</span>
          <strong>新しい順</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>日時</th>
              <th>判断</th>
              <th>対象</th>
              <th>理由</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  まだ記録がありません。資金移動の「承認」や物件の「見送り」から判断メモ付きで残ります。
                </td>
              </tr>
            ) : (
              rows.slice(0, 200).map((r) => (
                <tr key={r.key}>
                  <td className="meta" style={{ whiteSpace: "nowrap" }}>
                    {formatJstDateTime(r.at)}
                  </td>
                  <td>
                    <strong>{r.label}</strong>
                    <div className="meta">
                      {r.kind === "money" ? "資金移動" : "物件"}・{OUTCOME_LABEL[r.outcome]}
                    </div>
                  </td>
                  <td>
                    <a
                      href={
                        r.kind === "money"
                          ? "/money-ops"
                          : `/realestate/deals?deal=${encodeURIComponent(r.targetId)}`
                      }
                    >
                      {r.title}
                    </a>
                    {r.amountJpy !== null ? (
                      <div className="meta">{fmtYen(r.amountJpy)}</div>
                    ) : null}
                  </td>
                  <td>
                    {r.reasonLabels.length || r.always ? (
                      <div className="decision-tags">
                        {r.reasonLabels.map((l) => (
                          <span className="decision-tag" key={l}>
                            {l}
                          </span>
                        ))}
                        {r.always ? (
                          <span className="decision-tag always">次も同じに</span>
                        ) : null}
                      </div>
                    ) : null}
                    {r.note ? <div className="meta">{r.note}</div> : null}
                    {!r.reasonLabels.length && !r.note ? (
                      <span className="decision-empty-reason">理由なし</span>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
