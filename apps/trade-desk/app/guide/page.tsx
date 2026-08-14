import Shell from "@/components/Shell";
import {
  ASSET_LANES,
  ASSET_NAV_ITEMS,
  MAP_DOCS,
  OPS_LANES,
  PILLARS,
  PLAN_TAX_LANES,
  RE_LANES,
  SCREEN_LABELS,
  type MapItem,
} from "@/lib/kurashiftMap";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

function MapTable({ items }: { items: MapItem[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>記号／メニュー</th>
          <th>やりたいこと（役割）</th>
          <th>実装・画面</th>
        </tr>
      </thead>
      <tbody>
        {items.map((it) => (
          <tr key={it.id}>
            <td>
              <strong>{it.code}</strong>
              <div className="meta">{it.title}</div>
            </td>
            <td>
              {it.intent}
              {it.href ? (
                <div className="meta" style={{ marginTop: 4 }}>
                  <a href={it.href}>開く →</a>
                </div>
              ) : null}
            </td>
            <td className="meta">{it.implemented}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function GuidePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <Shell active="/guide" email={user?.email ?? null}>
      <h1>構成ガイド</h1>
      <p className="sub">
        サイドバー各メニューの役割と、①②③の記号をここで確認できます。
        ナビ上は「運用」グループにあります（本線の①②③からは外しています）。
      </p>

      <div className="card notice">
        <header>
          <span className="lvl">読み方</span>
          <strong>3本柱 → 各メニューの役割 → 画面内ラベル</strong>
        </header>
        <ul className="meta" style={{ marginTop: 8, paddingLeft: 18 }}>
          <li>
            <strong>①②③</strong> = やりたいことの大きな分類（サイドバーの見出し）
          </li>
          <li>
            <strong>各メニュー名</strong>（ホーム・テーマ・資金移動…）=
            その分類の中の具体的な役割。下表で説明
          </li>
          <li>
            <strong>①-A / ①-B / ①-C</strong> = 資産運用の考え方（把握／判断／日常）
          </li>
          <li>
            <strong>③-A〜D</strong> = 不動産の正式レーン
          </li>
          <li>
            <strong>運用</strong> = 地図・ジョブ・設定・実験（本線の外）
          </li>
          <li>
            <strong>KPI / Portfolio / Jobs など</strong> =
            レーン内の見出し。別レーンではない
          </li>
        </ul>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">柱</span>
          <strong>やりたいこと（大きな3本）</strong>
        </header>
        <div style={{ marginTop: 8 }}>
          <MapTable items={PILLARS} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }} id="asset-nav">
        <header>
          <span className="lvl">①</span>
          <strong>資産運用 — サイドバー各メニュー</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          「テーマと資金移動はどう違う？」など、メニュー単位の役割はここ。
        </p>
        <div style={{ marginTop: 8 }}>
          <MapTable items={ASSET_NAV_ITEMS} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }} id="asset-lanes">
        <header>
          <span className="lvl">①</span>
          <strong>資産運用の考え方（A / B / C）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          ホームの「①-C」は日常回し。Aは把握、Bはテーマや資金移動の判断です。
        </p>
        <div style={{ marginTop: 8 }}>
          <MapTable items={ASSET_LANES} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }} id="plan-tax">
        <header>
          <span className="lvl">②</span>
          <strong>計画・税 — 各メニュー</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          年数回〜申告期に触る枠。毎日の寄せ・売買判断は①側です。
        </p>
        <div style={{ marginTop: 8 }}>
          <MapTable items={PLAN_TAX_LANES} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }} id="re-lanes">
        <header>
          <span className="lvl">③</span>
          <strong>不動産レーン（正式）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          保有の運用と購入検討を混ぜないための分割です。Bは計画／実行に分かれます。
        </p>
        <div style={{ marginTop: 8 }}>
          <MapTable items={RE_LANES} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }} id="ops">
        <header>
          <span className="lvl">運用</span>
          <strong>本線の外（地図・ジョブ・設定・実験）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          構成ガイド自身もここにあります。判断の本線（①②③）と混ぜないためです。
        </p>
        <div style={{ marginTop: 8 }}>
          <MapTable items={OPS_LANES} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">注</span>
          <strong>画面内ラベル（レーンではない）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          「A, B, K, P, J, C, D」のように見えたときの読み替えです。K≈KPI、P≈Portfolio、J≈Jobs。
        </p>
        <div style={{ marginTop: 8 }}>
          <MapTable items={SCREEN_LABELS} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">Docs</span>
          <strong>詳細ドキュメント</strong>
        </header>
        <ul className="meta" style={{ marginTop: 8, paddingLeft: 18 }}>
          {MAP_DOCS.map((d) => (
            <li key={d.path}>
              {d.label}: <code>{d.path}</code>
            </li>
          ))}
        </ul>
      </div>
    </Shell>
  );
}
