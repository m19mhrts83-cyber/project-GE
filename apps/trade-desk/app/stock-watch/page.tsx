import EnqueueJobButton from "@/components/EnqueueJobButton";
import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

type WatchRow = {
  symbol?: string;
  name?: string;
  theme_title?: string;
  theme_id?: string;
  active?: boolean;
  bottom_hint?: number;
  upside_target_pct?: number;
  sell_drawdown_pct?: number;
};

type OrderPayload = {
  amount_jpy?: number;
  close?: number;
  signals?: string[];
  odd_lot?: boolean;
  money_path?: string;
  theme_title?: string;
};

type OrderRow = {
  id?: string;
  symbol?: string;
  side?: string;
  qty?: number;
  limit_price?: number;
  status?: string;
  created_at?: string;
  payload?: OrderPayload | null;
};

type Summary = {
  evaluated?: number;
  signals?: number;
  kinds?: string[];
  at?: string;
};

function parseJson<T>(raw: string | null | undefined): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export default async function StockWatchPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: metaRows } = await supabase
    .from("sync_meta")
    .select("key, value, updated_at")
    .in("key", [
      "stock_watch_at",
      "stock_watch_summary",
      "stock_watch_watches",
    ]);

  const meta: Record<string, { value: string; updated_at?: string }> = {};
  for (const r of metaRows || []) {
    meta[r.key] = { value: r.value, updated_at: r.updated_at };
  }

  const summary = parseJson<Summary>(meta.stock_watch_summary?.value);
  const watchesObj =
    parseJson<Record<string, WatchRow>>(meta.stock_watch_watches?.value) || {};
  const watches = Object.values(watchesObj);
  const active = watches.filter((w) => w.active);
  const inactive = watches.filter((w) => !w.active);

  const { data: orderRows } = await supabase
    .from("trade_orders")
    .select("id, symbol, side, qty, limit_price, status, created_at, payload")
    .eq("mode", "live")
    .in("status", ["preview", "confirmed"])
    .order("created_at", { ascending: false })
    .limit(20);
  const orders = (orderRows || []) as OrderRow[];

  return (
    <Shell active="/stock-watch" email={user?.email ?? null}>
      <h1>株式ウォッチ</h1>
      <p className="sub">
        Theme 衛星スリーブの閾値監視。判断・確認・動きは Todoist「Theme株式」。
        Phase1 は<strong>自動発注なし</strong>（立花 API はアプリ開発の未着手）。
      </p>

      <div className="card notice" style={{ marginBottom: 16 }}>
        <header>
          <span className="lvl">鮮度</span>
          <strong>{meta.stock_watch_at?.value || "未実行"}</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          最終評価: 監視 {summary?.evaluated ?? "—"} 銘柄 / シグナル{" "}
          {summary?.signals ?? "—"}
          {summary?.kinds?.length
            ? `（${summary.kinds.join(", ")}）`
            : ""}
        </p>
        <p className="meta">
          発注前プレビュー→対外確認ゲート: プレビューを作成し、Todoist
          Theme株式でオーナー確認後に確定。確定しても実発注はせず、手動アシスト手順を出します。
        </p>
      </div>

      <div className="grid">
        <article className="card">
          <header>
            <span className="lvl">監視中</span>
            <strong>{active.length} 銘柄</strong>
          </header>
          {active.length === 0 ? (
            <p className="meta">まだ監視ONの銘柄はありません。</p>
          ) : (
            <ul className="meta" style={{ marginTop: 8 }}>
              {active.map((w) => (
                <li key={w.symbol}>
                  <strong>{w.name || w.symbol}</strong>（{w.symbol}）
                  底値目安{" "}
                  {w.bottom_hint != null
                    ? Number(w.bottom_hint).toFixed(1)
                    : "—"}
                  {" / "}上昇目標 {w.upside_target_pct ?? "—"}%
                  {" / "}売下落 {w.sell_drawdown_pct ?? "—"}%
                  {w.theme_id ? (
                    <>
                      {" · "}
                      <a href={`/themes/${w.theme_id}`}>Theme</a>
                    </>
                  ) : null}
                  {w.symbol ? (
                    <div style={{ marginTop: 6 }}>
                      <EnqueueJobButton
                        jobType="stock_order_preview"
                        title={`[発注preview] ${w.name || w.symbol}`}
                        payload={{ symbol: w.symbol }}
                        label="発注プレビューを作成"
                      />
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="card">
          <header>
            <span className="lvl">提案・承認待ち</span>
            <strong>{inactive.length}</strong>
          </header>
          {inactive.length === 0 ? (
            <p className="meta">なし</p>
          ) : (
            <ul className="meta" style={{ marginTop: 8 }}>
              {inactive.map((w) => (
                <li key={w.symbol || w.theme_title}>
                  {w.theme_title || w.name || w.symbol}
                  {w.theme_id ? (
                    <>
                      {" · "}
                      <a href={`/themes/${w.theme_id}`}>開く</a>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">対外確認ゲート</span>
          <strong>発注プレビュー（承認待ち {orders.length}）</strong>
        </header>
        {orders.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            承認待ちはありません。監視中銘柄の「発注プレビューを作成」で起票します。
          </p>
        ) : (
          <ul className="meta" style={{ marginTop: 8 }}>
            {orders.map((o) => {
              const p = o.payload || {};
              return (
                <li key={o.id}>
                  <strong>
                    {o.symbol} {o.side === "sell" ? "売り" : "買い"} {o.qty}株
                  </strong>{" "}
                  指値 {o.limit_price}円 / 想定{" "}
                  {p.amount_jpy != null
                    ? Number(p.amount_jpy).toLocaleString()
                    : "—"}
                  円{" "}
                  <span className="meta">
                    [{o.status}] {p.signals?.join(", ")}
                    {p.odd_lot ? " · 単元未満" : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        <p className="meta" style={{ marginTop: 8 }}>
          確定はオーナー確認後のみ（CLI:{" "}
          <code>
            jarvis_kurashift_stock_order.py --confirm &lt;ID&gt;
            --i-confirm-order
          </code>
          ）。確定しても実発注せず手動アシスト手順を出します。
        </p>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">手順</span>
          <strong>購入アシスト（手動）</strong>
        </header>
        <ol className="meta" style={{ marginTop: 8, paddingLeft: 18 }}>
          <li>Todoist Theme株式で閾値コメントを確認</li>
          <li>Theme を承認（または <code>--activate-theme</code>）</li>
          <li>「発注プレビューを作成」→ Todoist オーナー確認で内容を確認</li>
          <li>確認OKなら <code>--confirm</code>（対外確認ゲート）で手順を確定</li>
          <li>立花等で単元・金額を確認して手動発注</li>
          <li>Todoist に「買った／見送り」コメント → オーナー確認経由で完了</li>
        </ol>
        <p className="meta" style={{ marginTop: 8 }}>
          <a href="/themes">テーマ一覧</a>
          {" · "}
          <a href="/paper">Lab（別系統・降格）</a>
        </p>
      </div>
    </Shell>
  );
}
