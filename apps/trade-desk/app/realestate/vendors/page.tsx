import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import {
  VENDOR_STATUS_LABEL,
  vendorNeedsFollowUp,
} from "@/lib/rePipelineUi";
import Link from "next/link";

export const dynamic = "force-dynamic";

const FILTERS: { id: string; label: string }[] = [
  { id: "followup", label: "要フォロー" },
  { id: "all", label: "すべて" },
  { id: "pending", label: "未送信" },
  { id: "contacted", label: "送信済" },
  { id: "replied", label: "返信あり" },
  { id: "excluded", label: "除外" },
];

function chipStyle(status: string): Record<string, string | number> {
  const base: Record<string, string | number> = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 4,
    fontSize: 12,
    border: "1px solid var(--border, #ccc)",
  };
  if (status === "replied") return { ...base, background: "#ecfdf5" };
  if (status === "contacted") return { ...base, background: "#eff6ff" };
  if (status === "pending" || status === "discovered")
    return { ...base, background: "#f8fafc" };
  return base;
}

export default async function RealEstateVendorsPage({
  searchParams,
}: {
  searchParams?: Promise<{ filter?: string }>;
}) {
  const sp = (await searchParams) || {};
  const filter = (sp.filter || "followup").trim();

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: vendors, error } = await supabase
    .from("kurashift_re_vendors")
    .select("*")
    .order("contacted_at", { ascending: false, nullsFirst: false })
    .order("updated_at", { ascending: false })
    .limit(500);

  const { data: deals } = await supabase
    .from("kurashift_re_deals")
    .select("id, summary_json")
    .limit(500);

  const dealCountByVendor = new Map<string, number>();
  for (const d of deals || []) {
    const sj =
      d.summary_json && typeof d.summary_json === "object"
        ? (d.summary_json as { vendor_id?: string })
        : {};
    if (sj.vendor_id) {
      dealCountByVendor.set(
        sj.vendor_id,
        (dealCountByVendor.get(sj.vendor_id) || 0) + 1
      );
    }
  }

  let rows = vendors || [];
  if (filter === "pending") {
    rows = rows.filter((v) =>
      ["pending", "discovered"].includes(v.status || "")
    );
  } else if (filter === "contacted") {
    rows = rows.filter((v) => v.status === "contacted");
  } else if (filter === "replied") {
    rows = rows.filter((v) => v.status === "replied");
  } else if (filter === "excluded") {
    rows = rows.filter((v) => ["skip", "invalid"].includes(v.status || ""));
  } else if (filter === "followup") {
    rows = rows.filter((v) => vendorNeedsFollowUp(v));
  }

  const counts: Record<string, number> = {};
  for (const v of vendors || []) {
    const st = v.status || "pending";
    counts[st] = (counts[st] || 0) + 1;
  }

  let latestSync: string | null = null;
  for (const v of vendors || []) {
    const s = v.synced_at as string | undefined;
    if (s && (!latestSync || s > latestSync)) latestSync = s;
  }

  const dailyLimit = 3;

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="b-vendors" />
      <p className="page-kicker">③-B開 · 業者開拓</p>
      <h1>業者開拓ウォッチ</h1>
      <p className="sub">
        地場リストへの Web 問合せ（「物件情報をください」）の送信状況。正本は Mac の{" "}
        <code>kurashift_re_vendor_list.yaml</code>。Grok 本日分の{" "}
        <code>--mark</code> 反映後に「リストを同期」してください。
      </p>

      <div className="card">
        <header>
          <span className="lvl">Summary</span>
          <strong>件数</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          未送信 {counts.pending || 0} · 探索 {counts.discovered || 0} · 送信済{" "}
          {counts.contacted || 0} · 返信あり {counts.replied || 0} · スキップ{" "}
          {counts.skip || 0}
        </p>
        <p className="meta">
          本日上限 {dailyLimit}/日 · 最終同期{" "}
          {latestSync
            ? latestSync.slice(0, 16).replace("T", " ")
            : "—（未同期）"}
        </p>
        <p style={{ marginTop: 10 }}>
          <EnqueueJobButton
            jobType="re_vendor_sync"
            title="業者リストを Supabase へ投影"
            label="リストを同期"
            payload={{}}
          />
        </p>
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: 16,
        }}
      >
        {FILTERS.map((f) => {
          const on = filter === f.id;
          return (
            <Link
              key={f.id}
              href={`/realestate/vendors?filter=${f.id}`}
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
                    }
              }
            >
              {f.label}
            </Link>
          );
        })}
      </div>

      <div className="card">
        <header>
          <span className="lvl">Vendors</span>
          <strong>
            一覧（{rows.length} 件
            {filter !== "all" ? ` · ${FILTERS.find((f) => f.id === filter)?.label}` : ""}
            ）
          </strong>
        </header>
        {error ? (
          <p className="meta" style={{ color: "var(--danger, #b45309)" }}>
            {error.message} — migration 未適用の可能性があります
          </p>
        ) : rows.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            {vendors?.length === 0
              ? "YAML 未取込 or 未同期 → Mac で import 後「リストを同期」"
              : "このフィルタに該当する業者はありません"}
          </p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>状態</th>
                  <th>業者名</th>
                  <th>エリア</th>
                  <th>問合せURL</th>
                  <th>送信日</th>
                  <th>返信日</th>
                  <th>備考</th>
                  <th>物件</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((v) => {
                  const dc = dealCountByVendor.get(v.id) || 0;
                  const opsOnly =
                    v.ops_contacted_at &&
                    !v.contacted_at &&
                    (v.status === "pending" || v.status === "discovered");
                  return (
                    <tr key={v.id}>
                      <td>
                        <span
                          style={chipStyle(v.status || "pending")}
                          title={(v.last_result || "").slice(0, 80)}
                        >
                          {VENDOR_STATUS_LABEL[v.status || "pending"] ||
                            v.status}
                        </span>
                        {opsOnly ? (
                          <div className="meta" style={{ marginTop: 2 }}>
                            運営のみ
                          </div>
                        ) : null}
                      </td>
                      <td>{v.name}</td>
                      <td className="meta">
                        {[v.prefecture, v.city].filter(Boolean).join(" ") ||
                          v.area ||
                          "—"}
                      </td>
                      <td className="meta">
                        {v.contact_url ? (
                          <a
                            href={v.contact_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            フォーム ↗
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="meta">{v.contacted_at || "—"}</td>
                      <td className="meta">{v.replied_at || "—"}</td>
                      <td className="meta">
                        {(v.notes || v.last_result || "—").slice(0, 40)}
                      </td>
                      <td className="meta">
                        {dc > 0 ? (
                          <Link href={`/realestate/deals?vendor=${v.id}`}>
                            {dc} 件
                          </Link>
                        ) : (
                          "—"
                        )}
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
