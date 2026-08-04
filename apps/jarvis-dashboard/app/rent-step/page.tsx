import Link from "next/link";
import Shell from "@/components/Shell";
import RentStepAckButton from "@/components/RentStepAckButton";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "rent_step";

type UnitRow = {
  id?: string;
  label?: string;
  flag?: string;
  manager?: string | null;
  book_rent?: number | null;
  expected_rent?: number | null;
  year1_rent?: number | null;
  year2_rent?: number | null;
  observed_deposit?: number | null;
  deposit_source?: string | null;
  deposit_ym?: string | null;
  deposit_gap_yen?: number | null;
  deposit_flag?: string | null;
  move_in?: string | null;
  anniversary?: string | null;
  reason?: string;
};

type AggregateRow = {
  group?: string;
  title?: string;
  bank_label?: string;
  bank_note?: string;
  book_rent_sum?: number | null;
  observed_yen?: number | null;
  observed_ym?: string | null;
  gap_yen?: number | null;
  memo?: string | null;
  memo_key?: string;
  needs_memo?: boolean;
  missing_bank?: boolean;
  rooms?: string[];
  flag?: string;
};

type FollowDraft = {
  manager?: string;
  channel?: string;
  subject?: string;
  item_count?: number;
  draft_path?: string | null;
  send_path?: string | null;
  promote_hint?: string;
  preview?: string;
  items?: { label?: string; kind?: string; reason?: string; gap_yen?: number | null }[];
};

type ChangeRow = {
  id?: string;
  label?: string;
  from?: number | null;
  to?: number | null;
  target_month?: string;
};

function fmtYen(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

function flagLabel(flag: string | undefined) {
  switch (flag) {
    case "overdue":
      return "未反映";
    case "changed":
      return "変動";
    case "upcoming":
      return "まもなく";
    case "grace":
      return "様子見";
    case "deposit_mismatch":
      return "入金差";
    case "unknown":
      return "不明";
    case "skip":
      return "空室";
    default:
      return "OK";
  }
}

export default async function RentStepPage() {
  const supabase = await createClient();
  const { data: watch } = await supabase
    .from("watch_status")
    .select("*")
    .eq("id", WATCH_ID)
    .maybeSingle();

  const payload =
    watch?.payload && typeof watch.payload === "object"
      ? (watch.payload as Record<string, unknown>)
      : {};

  const summary =
    payload.rent_summary && typeof payload.rent_summary === "object"
      ? (payload.rent_summary as Record<string, unknown>)
      : {};

  const units = Array.isArray(payload.units)
    ? (payload.units as UnitRow[])
    : [];
  const aggregates = Array.isArray(payload.aggregates)
    ? (payload.aggregates as AggregateRow[])
    : [];
  const followPayload =
    payload.follow_drafts && typeof payload.follow_drafts === "object"
      ? (payload.follow_drafts as Record<string, unknown>)
      : {};
  const followDrafts = Array.isArray(followPayload.drafts)
    ? (followPayload.drafts as FollowDraft[])
    : [];
  const history = Array.isArray(payload.change_history)
    ? (payload.change_history as ChangeRow[])
    : [];

  const ack =
    typeof payload.dashboard_ack_target_month === "string"
      ? payload.dashboard_ack_target_month
      : null;
  const target =
    typeof payload.target_month === "string" ? payload.target_month : null;
  const actionable = Boolean(summary.actionable);
  const has =
    target != null &&
    (actionable ||
      Number(summary.overdue_count || 0) > 0 ||
      Number(summary.changed_count || 0) > 0 ||
      Number(summary.deposit_mismatch_count || 0) > 0 ||
      Number(summary.aggregate_need_count || 0) > 0 ||
      Number(followPayload.follow_count || 0) > 0 ||
      followDrafts.length > 0);
  const showBanner =
    typeof payload.show_banner === "boolean"
      ? payload.show_banner
      : Boolean(has && ack !== target);

  const delta =
    typeof payload.delta_yen === "number" ? payload.delta_yen : 4000;

  const focusUnits = units.filter((u) =>
    ["overdue", "changed", "upcoming", "deposit_mismatch", "grace"].includes(
      u.flag || "",
    ),
  );

  return (
    <Shell active="/rent-step">
      <h1>Grandole 家賃ステップ</h1>
      <p className="sub">
        入居1年で +{delta.toLocaleString("ja-JP")}
        円（空室対策メール正本・入居日ズバリ）。未反映は記念日+30日以降。入金フォローは様子見後に下書き。
      </p>

      {showBanner && has && target ? (
        <article className="card level-info etc-rebate-banner">
          <header>
            <span className="lvl">確認</span>
            <strong>{target}分の家賃・入金チェック</strong>
          </header>
          <div className="etc-rebate-hero">
            <div>
              <span className="meta">未反映</span>
              <strong className="etc-rebate-yen">
                {Number(summary.overdue_count || 0)}件
              </strong>
            </div>
            <div>
              <span className="meta">様子見</span>
              <strong>{Number(summary.grace_count || 0)}件</strong>
            </div>
            <div>
              <span className="meta">入金差</span>
              <strong>{Number(summary.deposit_mismatch_count || 0)}件</strong>
            </div>
            <div>
              <span className="meta">入金様子見</span>
              <strong>
                {Number(
                  followPayload.watch_count ||
                    summary.follow_watch_count ||
                    0,
                )}
                件
              </strong>
            </div>
            <div>
              <span className="meta">フォロー下書き</span>
              <strong>
                {Number(
                  followPayload.draft_count ||
                    followDrafts.length ||
                    summary.follow_draft_count ||
                    0,
                )}
                件
              </strong>
            </div>
          </div>
          <p className="sum">
            {(payload.grant_rule as string) ||
              "I=PayPay / II=MUFG / キャラメル=滋賀 / LEAF現行=京都（変更予定）"}
          </p>
          {payload.note ? (
            <p className="meta">{String(payload.note)}</p>
          ) : null}
          <RentStepAckButton targetMonth={target} />
        </article>
      ) : has && target ? (
        <article className="card level-ok etc-rebate-banner is-acked">
          <header>
            <span className="lvl">確認済</span>
            <strong>{target}分は確認済み</strong>
          </header>
          <p className="sum">次の表示は翌月の更新後です。</p>
        </article>
      ) : (
        <article className="card">
          <p className="sum">いま要確認の家賃・入金はありません。</p>
        </article>
      )}

      <section className="etc-guide" aria-label="口座とソース">
        <h2>入金ソース・口座</h2>
        <ul className="etc-guide-list">
          <li>
            <strong>LEAF</strong> — くらさぽ PDF。現行振込先は京都銀行（変更予定）
          </li>
          <li>
            <strong>ミニテック</strong> — オーナーサイト送金案内 PDF（号室別）
          </li>
          <li>
            <strong>Tcell</strong> — LINE 明細 PDF。無いときは物件口座合算＋メモ（I→PayPay／キャラメル→滋賀）
          </li>
          <li>
            <strong>ホームプランナー</strong> — 紙明細のため MUFG 合算＋メモ（
            <code>config/rent_step_up.yaml</code> の <code>aggregate_memos</code>）
          </li>
        </ul>
      </section>

      <section>
        <h2>入金フォロー（様子見 → 下書き）</h2>
        <p className="meta">
          想定入金が確認できない場合も、すぐ催促しません（送金月ベースで約1ヶ月様子見）。
          経過後に <code>4.送信下書き_家賃入金フォロー.txt</code>{" "}
          を作成。正本の想定家賃は空室対策メールです。
        </p>
        {Array.isArray(followPayload.watching) &&
        (followPayload.watching as { label?: string }[]).length > 0 ? (
          <div className="card" style={{ marginBottom: 12 }}>
            <header>
              <span className="lvl">様子見</span>
              <strong>入金フォロー待ち</strong>
            </header>
            <ul className="etc-guide-list">
              {(
                followPayload.watching as {
                  manager?: string;
                  label?: string;
                  reason?: string;
                }[]
              ).map((w, i) => (
                <li key={`${w.label}-${i}`}>
                  {w.manager} {w.label}: {w.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {followDrafts.length === 0 ? (
          <p className="empty">いま送信可能な下書きはありません</p>
        ) : (
          <div className="card-list">
            {followDrafts.map((d) => (
              <article className="card" key={`${d.manager}-${d.subject}`}>
                <header>
                  <span className="lvl">
                    {d.channel === "email" ? "メール" : "LINEメモ"}
                  </span>
                  <strong>{d.manager}</strong>
                  <span className="meta"> · {d.item_count || 0}件</span>
                </header>
                <p className="sum">{d.subject}</p>
                <ul className="etc-guide-list">
                  {(d.items || []).map((it, i) => (
                    <li key={`${it.label}-${i}`}>
                      {it.label}: {it.reason}
                    </li>
                  ))}
                </ul>
                {d.preview ? (
                  <pre className="meta" style={{ whiteSpace: "pre-wrap" }}>
                    {d.preview}
                  </pre>
                ) : null}
                {d.draft_path ? (
                  <p className="meta">保存先: {d.draft_path}</p>
                ) : null}
                {d.promote_hint ? (
                  <p className="meta">送信準備: {d.promote_hint}</p>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>口座合算（HP / Tcell明細なし / LEAF欠落）</h2>
        {aggregates.length === 0 ? (
          <p className="empty">該当なし</p>
        ) : (
          <div className="prop-event-table-wrap" style={{ maxHeight: "min(320px, 45vh)" }}>
            <table className="prop-event-table">
              <thead>
                <tr>
                  <th>区分</th>
                  <th>口座</th>
                  <th>帳簿合計</th>
                  <th>入金合算</th>
                  <th>差</th>
                  <th>メモ</th>
                </tr>
              </thead>
              <tbody>
                {aggregates.map((a) => (
                  <tr key={`${a.group}-${a.title}`}>
                    <td>
                      <strong>{a.title}</strong>
                      <div className="meta">{(a.rooms || []).join(", ")}</div>
                    </td>
                    <td className="meta">
                      {a.bank_label}
                      {a.observed_ym ? ` · ${a.observed_ym}` : ""}
                    </td>
                    <td>{fmtYen(a.book_rent_sum)}</td>
                    <td>{fmtYen(a.observed_yen)}</td>
                    <td>{fmtYen(a.gap_yen)}</td>
                    <td className="prop-note">
                      {a.needs_memo ? (
                        <>
                          要メモ: <code>{a.memo_key}</code>
                        </>
                      ) : (
                        a.memo || a.bank_note || "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2>要フォロー号室</h2>
        {focusUnits.length === 0 ? (
          <p className="empty">該当なし</p>
        ) : (
          <div className="prop-event-table-wrap" style={{ maxHeight: "min(360px, 50vh)" }}>
            <table className="prop-event-table">
              <thead>
                <tr>
                  <th>区分</th>
                  <th>号室</th>
                  <th>管理</th>
                  <th>帳簿</th>
                  <th>入金</th>
                  <th>理由</th>
                </tr>
              </thead>
              <tbody>
                {focusUnits.map((u) => (
                  <tr key={u.id || u.label}>
                    <td>{flagLabel(u.flag)}</td>
                    <td>
                      <strong>{u.label}</strong>
                    </td>
                    <td className="meta">{u.manager || "—"}</td>
                    <td>{fmtYen(u.book_rent)}</td>
                    <td>
                      {fmtYen(u.observed_deposit)}
                      {u.deposit_ym ? (
                        <span className="meta"> · {u.deposit_ym}</span>
                      ) : null}
                    </td>
                    <td className="prop-note">{u.reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2>全号室</h2>
        <div className="prop-event-table-wrap">
          <table className="prop-event-table">
            <thead>
              <tr>
                <th>区分</th>
                <th>号室</th>
                <th>管理</th>
                <th>帳簿</th>
                <th>入金観測</th>
                <th>ソース</th>
                <th>入居</th>
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr key={u.id || u.label}>
                  <td>{flagLabel(u.flag)}</td>
                  <td>{u.label}</td>
                  <td className="meta">{u.manager || "—"}</td>
                  <td>{fmtYen(u.book_rent)}</td>
                  <td>
                    {fmtYen(u.observed_deposit)}
                    {u.deposit_gap_yen != null ? (
                      <span className="meta">
                        {" "}
                        ({u.deposit_gap_yen >= 0 ? "+" : ""}
                        {u.deposit_gap_yen.toLocaleString("ja-JP")})
                      </span>
                    ) : null}
                  </td>
                  <td className="meta">
                    {u.deposit_source || u.deposit_flag || "—"}
                    {u.deposit_ym ? ` ${u.deposit_ym}` : ""}
                  </td>
                  <td className="meta">{u.move_in || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>過去の家賃変動</h2>
        {history.length === 0 ? (
          <p className="empty">履歴はまだありません</p>
        ) : (
          <ul className="etc-history-list">
            {history.map((h, i) => (
              <li key={`${h.id}-${h.to}-${i}`}>
                <strong>{h.label || h.id}</strong>
                {" · "}
                {fmtYen(h.from)} → {fmtYen(h.to)}
                {h.target_month ? (
                  <span className="meta"> · {h.target_month}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="sub" style={{ marginTop: 16 }}>
        <Link href="/properties">所有物件 →</Link>
        {" · "}
        <Link href="/situation">状況ウォッチ →</Link>
      </p>
    </Shell>
  );
}
