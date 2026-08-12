import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

const CHECKLIST: { id: string; title: string; note: string }[] = [
  {
    id: "id",
    title: "本人確認（免許証等）",
    note: "融資申込時の必須一式",
  },
  {
    id: "income",
    title: "収入証明（源泉・確定申告）",
    note: "個人／法人でセットが異なる",
  },
  {
    id: "corp",
    title: "法人関連（登記・決算）",
    note: "法人案件時。`.env` の COMPANY_* と突合予定",
  },
  {
    id: "property",
    title: "物件資料（登記・図面・レントロール）",
    note: "③-C 物件マスタ＋買い進め案件から生成予定",
  },
  {
    id: "loan",
    title: "既存借入一覧",
    note: "正本は借入残高トラッカー（読取投影後に埋め込み）",
  },
  {
    id: "bank",
    title: "銀行別・提出フォーマット",
    note: "240_融資フォルダの銀行別テンプレを参照",
  },
];

export default async function FinancePackPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { count: unitCount } = await supabase
    .from("property_units")
    .select("id", { count: "exact", head: true });

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <p className="page-kicker">③-D · 融資</p>
      <h1>融資提出パック</h1>
      <p className="sub">
        銀行提出用の書類チェックリスト骨格。自動送信・自動アップロードはしません。
        {" · "}
        <a href="/realestate">不動産ハブ →</a>
        {" · "}
        <a href="/realestate/properties">物件マスタ →</a>
      </p>

      <div className="card notice">
        <header>
          <span className="lvl">現状</span>
          <strong>Phase 0（チェックリスト）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          号室データ {unitCount ?? 0} 件を参照可能。PDF 一括出力・状態保存は未実装。
          OneDrive 正本: <code>240_融資</code>。
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Checklist</span>
          <strong>提出物（仮）</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>項目</th>
              <th>状態</th>
              <th>メモ</th>
            </tr>
          </thead>
          <tbody>
            {CHECKLIST.map((c) => (
              <tr key={c.id}>
                <td>{c.title}</td>
                <td className="meta">未着手</td>
                <td className="meta">{c.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">依存</span>
          <strong>次に揃えるもの</strong>
        </header>
        <ul className="meta" style={{ paddingLeft: 18 }}>
          <li>loan-tracker 読取投影（既存借入一覧の自動埋込）</li>
          <li>銀行ごとの必須項目マスタ（ユーザー確認後）</li>
          <li>案件（③-B）から「この物件用パック」を切る UI</li>
        </ul>
      </div>
    </Shell>
  );
}
