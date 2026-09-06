import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import {
  ALIVE_STATUS_LABEL,
  VENDOR_STATUS_LABEL,
  vendorAliveEffective,
  vendorAliveOk,
  vendorNeedsFollowUp,
} from "@/lib/rePipelineUi";
import Link from "next/link";

export const dynamic = "force-dynamic";

const FILTERS: { id: string; label: string }[] = [
  { id: "all", label: "すべて" },
  { id: "rank-a", label: "推奨A (一人親方)" },
  { id: "rank-b", label: "推奨B (地域密着)" },
  { id: "alive", label: "すぐ連絡可 (生存OK)" },
  { id: "followup", label: "要フォロー" },
  { id: "pending", label: "候補一覧" },
  { id: "contacted", label: "連絡済" },
  { id: "excluded", label: "除外" },
];

const TRADE_LABELS: Record<string, string> = {
  plumbing: "水廻り",
  electric: "電気",
  interior: "内装",
  multi: "多能工・便利屋",
  roof: "屋根・雨樋",
  塗装: "外壁塗装",
  残置物: "残置物撤去",
};

function chipStyle(status: string): Record<string, string | number> {
  const base: Record<string, string | number> = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 4,
    fontSize: 12,
    border: "1px solid var(--border, #ccc)",
  };
  if (status === "replied" || status === "ok")
    return { ...base, background: "#ecfdf5", color: "#065f46" };
  if (status === "contacted") return { ...base, background: "#eff6ff", color: "#1e40af" };
  if (status === "fail" || status === "stale")
    return { ...base, background: "#fff7ed", color: "#9a3412" };
  return base;
}

function recommendBadge(recommend?: string | null, soleScore?: string | null) {
  const r = (recommend || "").toUpperCase();
  const s = (soleScore || "").toLowerCase();

  if (r === "A" || s === "high") {
    return {
      rank: "A",
      label: "推奨 A (一人親方)",
      stars: "★★★",
      bg: "#d1fae5",
      border: "#10b981",
      color: "#065f46",
    };
  }
  if (r === "B" || s === "mid") {
    return {
      rank: "B",
      label: "推奨 B (地域密着)",
      stars: "★★",
      bg: "#dbeafe",
      border: "#60a5fa",
      color: "#1e40af",
    };
  }
  if (r === "C" || s === "low") {
    return {
      rank: "C",
      label: "推奨 C (一般/大手)",
      stars: "★",
      bg: "#f1f5f9",
      border: "#cbd5e1",
      color: "#475569",
    };
  }
  if (r === "D") {
    return {
      rank: "D",
      label: "除外 D",
      stars: "✕",
      bg: "#fee2e2",
      border: "#f87171",
      color: "#991b1b",
    };
  }
  return {
    rank: "-",
    label: "未評価",
    stars: "—",
    bg: "#f8fafc",
    border: "#e2e8f0",
    color: "#64748b",
  };
}

export default async function RepairVendorsPage({
  searchParams,
}: {
  searchParams?: Promise<{ filter?: string; trade?: string; sort?: string }>;
}) {
  const sp = (await searchParams) || {};
  const filter = (sp.filter || "all").trim();
  const trade = (sp.trade || "").trim();
  const sort = (sp.sort || "rating").trim();

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: vendors, error } = await supabase
    .from("kurashift_re_repair_vendors")
    .select("*")
    .order("updated_at", { ascending: false })
    .limit(500);

  let rows = [...(vendors || [])];
  if (trade) {
    rows = rows.filter((v) => (v.trade || "") === trade);
  }
  if (filter === "rank-a") {
    rows = rows.filter(
      (v) =>
        (v.recommend || "").toUpperCase() === "A" ||
        (v.sole_proprietor_score || "").toLowerCase() === "high"
    );
  } else if (filter === "rank-b") {
    rows = rows.filter(
      (v) =>
        (v.recommend || "").toUpperCase() === "B" ||
        (v.sole_proprietor_score || "").toLowerCase() === "mid"
    );
  } else if (filter === "pending") {
    rows = rows.filter((v) =>
      ["pending", "discovered"].includes(v.status || "")
    );
  } else if (filter === "contacted") {
    rows = rows.filter((v) => v.status === "contacted");
  } else if (filter === "excluded") {
    rows = rows.filter((v) => ["skip", "invalid"].includes(v.status || ""));
  } else if (filter === "alive") {
    rows = rows.filter((v) => vendorAliveOk(v));
  } else if (filter === "followup") {
    rows = rows.filter((v) => vendorNeedsFollowUp(v));
  }

  // ソートロジック
  rows.sort((a, b) => {
    if (sort === "alive") {
      const ao = vendorAliveOk(a) ? 0 : 1;
      const bo = vendorAliveOk(b) ? 0 : 1;
      if (ao !== bo) return ao - bo;
    }

    // レーティング評価優先 (A -> B -> C -> D -> 未評価)
    const rankOrder: Record<string, number> = { A: 1, B: 2, C: 3, D: 4 };
    const ra = rankOrder[recommendBadge(a.recommend, a.sole_proprietor_score).rank] || 9;
    const rb = rankOrder[recommendBadge(b.recommend, b.sole_proprietor_score).rank] || 9;
    if (ra !== rb) return ra - rb;

    // 次に生存OK優先
    const ao = vendorAliveOk(a) ? 0 : 1;
    const bo = vendorAliveOk(b) ? 0 : 1;
    if (ao !== bo) return ao - bo;

    return String(a.name || "").localeCompare(String(b.name || ""), "ja");
  });

  const counts: Record<string, number> = {};
  let aliveOk = 0;
  let rankACount = 0;
  let rankBCount = 0;
  let rankCCount = 0;
  const trades = new Set<string>();

  for (const v of vendors || []) {
    const st = v.status || "pending";
    counts[st] = (counts[st] || 0) + 1;
    if (vendorAliveOk(v)) aliveOk += 1;
    if (v.trade) trades.add(String(v.trade));

    const rb = recommendBadge(v.recommend, v.sole_proprietor_score);
    if (rb.rank === "A") rankACount += 1;
    else if (rb.rank === "B") rankBCount += 1;
    else if (rb.rank === "C") rankCCount += 1;
  }

  let latestSync: string | null = null;
  for (const v of vendors || []) {
    const s = v.synced_at as string | undefined;
    if (s && (!latestSync || s > latestSync)) latestSync = s;
  }

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="b-repair" />
      <p className="page-kicker">③-B開 · 修繕業者</p>
      <h1>修繕業者台帳（S4）</h1>
      <p className="sub">
        Grok S4（修繕業者開拓）が探索した業者台帳です。
        <strong>一人親方・地域密着のレーティング評価（推奨A〜C）</strong>および生存確認（90日以内）を管理します。
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <header>
          <span className="lvl">Summary</span>
          <strong>台帳サマリー（全 {vendors?.length || 0} 件）</strong>
        </header>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            marginTop: 10,
            marginBottom: 8,
          }}
        >
          <span
            style={{
              padding: "4px 10px",
              background: "#d1fae5",
              color: "#065f46",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 700,
              border: "1px solid #10b981",
            }}
          >
            ★★★ 推奨A (一人親方): {rankACount} 件
          </span>
          <span
            style={{
              padding: "4px 10px",
              background: "#dbeafe",
              color: "#1e40af",
              borderRadius: 6,
              fontSize: 13,
              fontWeight: 600,
              border: "1px solid #60a5fa",
            }}
          >
            ★★ 推奨B (地域密着): {rankBCount} 件
          </span>
          <span
            style={{
              padding: "4px 10px",
              background: "#ecfdf5",
              color: "#065f46",
              borderRadius: 6,
              fontSize: 13,
              border: "1px solid #a7f3d0",
            }}
          >
            📞 すぐ連絡可 (生存OK): {aliveOk} 件
          </span>
          <span
            style={{
              padding: "4px 10px",
              background: "#f8fafc",
              color: "#475569",
              borderRadius: 6,
              fontSize: 13,
              border: "1px solid #e2e8f0",
            }}
          >
            候補: {(counts.pending || 0) + (counts.discovered || 0)} 件 · 連絡済: {counts.contacted || 0} 件
          </span>
        </div>
        <p className="meta" style={{ marginTop: 6 }}>
          最終同期:{" "}
          {latestSync
            ? latestSync.slice(0, 16).replace("T", " ")
            : "—（未同期）"}
          （正本: Mac <code>config/kurashift_repair_vendor_list.yaml</code>）
        </p>
        <p style={{ marginTop: 10 }}>
          <EnqueueJobButton
            jobType="re_repair_vendor_sync"
            title="修繕業者リストを Supabase へ投影"
            label="リストを再同期"
            payload={{}}
          />
        </p>
      </div>

      {/* フィルタボタン */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: 12,
        }}
      >
        {FILTERS.map((f) => {
          const on = filter === f.id;
          const href = trade
            ? `/realestate/repair-vendors?filter=${f.id}&trade=${encodeURIComponent(trade)}`
            : `/realestate/repair-vendors?filter=${f.id}`;
          return (
            <Link
              key={f.id}
              href={href}
              className={on ? "btn" : undefined}
              style={
                on
                  ? undefined
                  : {
                      padding: "4px 10px",
                      border: "1px solid var(--border, #ccc)",
                      borderRadius: 6,
                      textDecoration: "none",
                      fontSize: 13,
                      background: "#fff",
                    }
              }
            >
              {f.label}
              {f.id === "all" ? ` (${vendors?.length || 0})` : ""}
              {f.id === "rank-a" ? ` (${rankACount})` : ""}
              {f.id === "rank-b" ? ` (${rankBCount})` : ""}
              {f.id === "alive" ? ` (${aliveOk})` : ""}
            </Link>
          );
        })}
      </div>

      {/* 職種フィルタ */}
      {trades.size > 0 ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: 6,
            marginBottom: 16,
            padding: "8px 12px",
            background: "#f8fafc",
            borderRadius: 6,
            border: "1px solid #e2e8f0",
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 600, color: "#64748b", marginRight: 4 }}>
            職種別:
          </span>
          <Link
            href={`/realestate/repair-vendors?filter=${filter}`}
            className={!trade ? "btn" : undefined}
            style={
              !trade
                ? undefined
                : {
                    padding: "2px 8px",
                    border: "1px solid var(--border, #ccc)",
                    borderRadius: 4,
                    textDecoration: "none",
                    fontSize: 12,
                    background: "#fff",
                  }
            }
          >
            全職種
          </Link>
          {[...trades].sort().map((t) => {
            const label = TRADE_LABELS[t] ? `${TRADE_LABELS[t]} (${t})` : t;
            return (
              <Link
                key={t}
                href={`/realestate/repair-vendors?filter=${filter}&trade=${encodeURIComponent(t)}`}
                className={trade === t ? "btn" : undefined}
                style={
                  trade === t
                    ? undefined
                    : {
                        padding: "2px 8px",
                        border: "1px solid var(--border, #ccc)",
                        borderRadius: 4,
                        textDecoration: "none",
                        fontSize: 12,
                        background: "#fff",
                      }
                }
              >
                {label}
              </Link>
            );
          })}
        </div>
      ) : null}

      {/* 一覧テーブル */}
      <div className="card">
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <div>
            <span className="lvl">Repair Vendors</span>
            <strong>
              業者一覧（{rows.length} 件
              {filter !== "all"
                ? ` · ${FILTERS.find((f) => f.id === filter)?.label}`
                : ""}
              {trade ? ` · ${TRADE_LABELS[trade] || trade}` : ""}）
            </strong>
          </div>
          <span className="meta" style={{ fontSize: 12 }}>
            ソート: レーティング評価（A→B→C）順 ＋ 生存OK優先
          </span>
        </header>

        {error ? (
          <p className="meta" style={{ color: "var(--danger, #b45309)" }}>
            {error.message} — migration 未適用の可能性があります
          </p>
        ) : rows.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            このフィルタに該当する修繕業者はありません。
          </p>
        ) : (
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table style={{ minWidth: 980, borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr style={{ background: "#f1f5f9", borderBottom: "2px solid #cbd5e1" }}>
                  <th style={{ width: 145, padding: "8px 10px" }}>レーティング評価</th>
                  <th style={{ width: 95, padding: "8px 10px" }}>生存確認</th>
                  <th style={{ width: 85, padding: "8px 10px" }}>状態</th>
                  <th style={{ width: 180, padding: "8px 10px" }}>業者名 / 屋号</th>
                  <th style={{ width: 110, padding: "8px 10px" }}>職種</th>
                  <th style={{ width: 120, padding: "8px 10px" }}>エリア</th>
                  <th style={{ width: 130, padding: "8px 10px" }}>電話 / 連絡先</th>
                  <th style={{ padding: "8px 10px" }}>備考・評価メモ</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((v) => {
                  const alive = vendorAliveEffective(v);
                  const badge = recommendBadge(v.recommend, v.sole_proprietor_score);
                  const tradeName = TRADE_LABELS[v.trade || ""] || v.trade || "—";

                  return (
                    <tr
                      key={v.id}
                      style={{
                        borderBottom: "1px solid #e2e8f0",
                        background: badge.rank === "A" ? "#fafffd" : "#fff",
                      }}
                    >
                      {/* レーティング評価 */}
                      <td style={{ verticalAlign: "top", padding: "10px 8px" }}>
                        <div
                          style={{
                            display: "inline-block",
                            padding: "3px 8px",
                            borderRadius: 4,
                            fontSize: 12,
                            fontWeight: 700,
                            background: badge.bg,
                            color: badge.color,
                            border: `1px solid ${badge.border}`,
                          }}
                        >
                          {badge.label}
                        </div>
                        {v.cost_rating || v.service_rating ? (
                          <div
                            style={{
                              fontSize: 11,
                              color: "#64748b",
                              marginTop: 4,
                              lineHeight: 1.3,
                            }}
                          >
                            {v.cost_rating ? `費用: ${v.cost_rating} ` : ""}
                            {v.service_rating ? `品質: ${v.service_rating}` : ""}
                          </div>
                        ) : null}
                      </td>

                      {/* 生存確認 */}
                      <td style={{ verticalAlign: "top", padding: "10px 8px" }}>
                        <span style={chipStyle(alive)}>
                          {ALIVE_STATUS_LABEL[alive] || alive}
                        </span>
                        {v.alive_checked_at ? (
                          <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>
                            {String(v.alive_checked_at).slice(5)}
                          </div>
                        ) : null}
                      </td>

                      {/* 状態 */}
                      <td style={{ verticalAlign: "top", padding: "10px 8px" }}>
                        <span style={chipStyle(v.status || "pending")}>
                          {VENDOR_STATUS_LABEL[v.status || "pending"] || v.status}
                        </span>
                      </td>

                      {/* 業者名 / 屋号 */}
                      <td style={{ verticalAlign: "top", padding: "10px 8px" }}>
                        <div style={{ fontWeight: 600, color: "#1e293b" }}>
                          {v.name}
                        </div>
                        <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                          {v.url ? (
                            <a
                              href={v.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                fontSize: 11,
                                color: "#2563eb",
                                textDecoration: "underline",
                              }}
                            >
                              Webサイト ↗
                            </a>
                          ) : null}
                          {v.contact_url && v.contact_url !== v.url ? (
                            <a
                              href={v.contact_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                fontSize: 11,
                                color: "#4f46e5",
                                textDecoration: "underline",
                              }}
                            >
                              問合せ先 ↗
                            </a>
                          ) : null}
                        </div>
                      </td>

                      {/* 職種 */}
                      <td style={{ verticalAlign: "top", padding: "10px 8px" }}>
                        <div style={{ fontWeight: 600, color: "#334155" }}>
                          {tradeName}
                        </div>
                        {tradeName !== v.trade && v.trade ? (
                          <div style={{ fontSize: 11, color: "#94a3b8" }}>
                            {v.trade}
                          </div>
                        ) : null}
                      </td>

                      {/* エリア */}
                      <td style={{ verticalAlign: "top", padding: "10px 8px" }}>
                        <div style={{ color: "#334155" }}>{v.area || "—"}</div>
                        {v.city && v.city !== v.area ? (
                          <div style={{ fontSize: 11, color: "#94a3b8" }}>
                            {v.city}
                          </div>
                        ) : null}
                      </td>

                      {/* 電話 */}
                      <td style={{ verticalAlign: "top", padding: "10px 8px" }}>
                        {v.phone ? (
                          <a
                            href={`tel:${v.phone.replace(/[^0-9]/g, "")}`}
                            style={{
                              fontWeight: 600,
                              color: "#0369a1",
                              textDecoration: "none",
                              fontSize: 13,
                            }}
                          >
                            📞 {v.phone}
                          </a>
                        ) : (
                          <span style={{ color: "#94a3b8" }}>—</span>
                        )}
                        {v.contact_email ? (
                          <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                            ✉️ {v.contact_email}
                          </div>
                        ) : null}
                      </td>

                      {/* 備考・評価メモ */}
                      <td style={{ verticalAlign: "top", padding: "10px 8px" }}>
                        <div style={{ fontSize: 12, color: "#334155", lineHeight: 1.4 }}>
                          {v.notes || v.alive_note || "—"}
                        </div>
                        {v.rating_evidence ? (
                          <div
                            style={{
                              fontSize: 11,
                              color: "#065f46",
                              background: "#ecfdf5",
                              padding: "2px 6px",
                              borderRadius: 4,
                              marginTop: 4,
                            }}
                          >
                            根拠: {v.rating_evidence}
                          </div>
                        ) : null}
                        {v.source ? (
                          <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 3 }}>
                            出典: {v.source}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Shell>
  );
}
