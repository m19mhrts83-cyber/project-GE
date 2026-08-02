import Link from "next/link";
import Shell from "@/components/Shell";
import RentStepAckButton from "@/components/RentStepAckButton";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "rent_step";

type UnitRow = {
  id?: string;
  label?: string;
  flag?: string;
  book_rent?: number | null;
  expected_rent?: number | null;
  year1_rent?: number | null;
  year2_rent?: number | null;
  move_in?: string | null;
  anniversary?: string | null;
  reason?: string;
  phase?: string;
};

type ChangeRow = {
  id?: string;
  label?: string;
  from?: number | null;
  to?: number | null;
  at?: string;
  target_month?: string;
  reason?: string;
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
      Number(summary.changed_count || 0) > 0);
  const showBanner =
    typeof payload.show_banner === "boolean"
      ? payload.show_banner
      : Boolean(has && ack !== target);

  const delta =
    typeof payload.delta_yen === "number" ? payload.delta_yen : 4000;
  const zaim =
    payload.zaim_hint && typeof payload.zaim_hint === "object"
      ? (payload.zaim_hint as Record<string, unknown>)
      : null;

  const focusUnits = units.filter((u) =>
    ["overdue", "changed", "upcoming"].includes(u.flag || ""),
  );

  return (
    <Shell active="/rent-step">
      <h1>Grandole 家賃ステップ</h1>
      <p className="sub">
        入居から1年で家賃 +{delta.toLocaleString("ja-JP")}
        円。月次で帳簿家賃と入居日起算を突合し、変動・未反映を確認します。
      </p>

      {showBanner && has && target ? (
        <article className="card level-info etc-rebate-banner">
          <header>
            <span className="lvl">確認</span>
            <strong>{target}分の家賃チェック</strong>
          </header>
          <div className="etc-rebate-hero">
            <div>
              <span className="meta">未反映</span>
              <strong className="etc-rebate-yen">
                {Number(summary.overdue_count || 0)}件
              </strong>
            </div>
            <div>
              <span className="meta">変動</span>
              <strong>{Number(summary.changed_count || 0)}件</strong>
            </div>
            <div>
              <span className="meta">まもなく2年目</span>
              <strong>{Number(summary.upcoming_count || 0)}件</strong>
            </div>
            <div>
              <span className="meta">OK</span>
              <strong>{Number(summary.ok_count || 0)}件</strong>
            </div>
          </div>
          <p className="sum">
            {(payload.grant_rule as string) ||
              "Grandole は入居1年で +4,000円。Excel／入金と突合して更新してください。"}
          </p>
          {zaim ? (
            <p className="meta">
              Zaim家賃収入ヒント: {String(zaim.previous_ym)}→
              {String(zaim.current_ym)}{" "}
              {fmtYen(Number(zaim.delta_yen))}
              （号室別ではない弱シグナル）
            </p>
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
          <p className="sum">
            いま要確認の家賃ステップはありません。毎月の situation watch / push
            で自動更新されます。
          </p>
        </article>
      )}

      <section className="etc-guide" aria-label="凡例">
        <h2>判定の見方</h2>
        <ul className="etc-guide-list">
          <li>
            <strong>未反映</strong> — 2年目に入ったが帳簿がまだ1年目帯（+{delta}
            未反映の疑い）
          </li>
          <li>
            <strong>変動</strong> — 前回スナップショットから帳簿家賃が変わった
          </li>
          <li>
            <strong>まもなく</strong> — 入居1年の切替まで45日以内
          </li>
          <li>
            入金の号室別突合は未連携。くらさぽ／管理会社明細のパースは今後。当面は
            Excel 帳簿＋Zaim 家賃収入を参考にします。
          </li>
        </ul>
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
                  <th>帳簿</th>
                  <th>期待</th>
                  <th>入居</th>
                  <th>1年後</th>
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
                    <td>{fmtYen(u.book_rent)}</td>
                    <td>{fmtYen(u.expected_rent)}</td>
                    <td className="meta">{u.move_in || "—"}</td>
                    <td className="meta">{u.anniversary || "—"}</td>
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
                <th>帳簿</th>
                <th>1年目</th>
                <th>2年目</th>
                <th>入居</th>
                <th>理由</th>
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr key={u.id || u.label}>
                  <td>{flagLabel(u.flag)}</td>
                  <td>{u.label}</td>
                  <td>{fmtYen(u.book_rent)}</td>
                  <td>{fmtYen(u.year1_rent)}</td>
                  <td>{fmtYen(u.year2_rent)}</td>
                  <td className="meta">{u.move_in || "—"}</td>
                  <td className="prop-note">{u.reason || "—"}</td>
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
