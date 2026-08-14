import Shell from "@/components/Shell";
import {
  ASSET_LANES,
  MAP_DOCS,
  PILLARS,
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
          <th>記号</th>
          <th>やりたいこと</th>
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
        人に説明するとき・自分で振り返るときに、記号の意味をここで確認できます。
        Cursor に聞かなくても、この画面が正本です。
      </p>

      <div className="card notice">
        <header>
          <span className="lvl">読み方</span>
          <strong>3本柱 → 各柱のレーン → 画面内ラベル</strong>
        </header>
        <ul className="meta" style={{ marginTop: 8, paddingLeft: 18 }}>
          <li>
            <strong>①②③</strong> = やりたいことの大きな分類
          </li>
          <li>
            <strong>①-A / ①-B / ①-C</strong> = 資産運用の中の3種類（ホームの「①-C」は日常回し）
          </li>
          <li>
            <strong>③-A〜D</strong> = 不動産の正式レーン（ナビに出るもの）
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

      <div className="card" style={{ marginTop: 16 }} id="asset-lanes">
        <header>
          <span className="lvl">①</span>
          <strong>資産運用の3種類（A / B / C）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          ホームに残っている「①-C 日常の短い回し方」は、このうち C
          です。Aは把握、Bはテーマや資金移動の判断です。
        </p>
        <div style={{ marginTop: 8 }}>
          <MapTable items={ASSET_LANES} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }} id="re-lanes">
        <header>
          <span className="lvl">③</span>
          <strong>不動産レーン（正式）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          調整の過程で画面に KPI・Portfolio・Jobs
          などの見出しが増えましたが、レーンの正は下表の5本（Bは計画／実行に分割）です。
        </p>
        <div style={{ marginTop: 8 }}>
          <MapTable items={RE_LANES} />
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
