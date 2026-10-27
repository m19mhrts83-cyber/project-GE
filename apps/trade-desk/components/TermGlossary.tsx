/** 画面に出る記号・略語の凡例（全画面共通・折りたたみ） */

const TERMS: { term: string; meaning: string }[] = [
  { term: "①②③", meaning: "3本柱。①資産運用 ②暮らしの計画と税 ③不動産賃貸経営" },
  { term: "①-A / ①-B / ①-C", meaning: "①資産運用の中身。A=週次の全体把握、B=提案→相談→承認→実行、C=日常の短い回し方" },
  { term: "③-A", meaning: "不動産の運用・進捗。今持っている物件が年間計画に対してどうか" },
  { term: "③-B（計・実・開）", meaning: "これから買う物件。計=買い進めプラン（長期）、実=物件探し（千三つ）、開=業者開拓" },
  { term: "③-C", meaning: "保有物件マスタ。号室・家賃・管理会社・ローン（借入残高トラッカーから投影）" },
  { term: "③-D", meaning: "融資提出パック。銀行に出す書類の一覧と不足確認" },
  { term: "千三つ", meaning: "情報1000件→内見100件→買付10件→購入3件、という物件探しの目安" },
  { term: "CF", meaning: "キャッシュフロー。家賃などの入金からローン返済・経費を引いて手元に残るお金" },
  { term: "DSCR", meaning: "家賃 ÷ ローン返済。1.0を下回ると家賃で返済をまかなえていない" },
  { term: "返済比率", meaning: "年間返済 ÷ 年間家賃収入。目安は50%前後" },
  { term: "B-RATE", meaning: "利回りと借入金利の表示。B-RATE-4 は残高で重み付けした合算金利" },
  { term: "α / β / γ / δ", meaning: "支出の分け方。α貯蓄20%・β生活60%・γ自己投資と教育20%、δは不動産（割合の分母に入れない）" },
  { term: "Core / Theme / Lab", meaning: "Core=触らない土台（NISA月9万など）、Theme=相談して動かす投資、Lab=小額の実験" },
  { term: "MQ（PQ・VQ・F・G）", meaning: "MQ会計。PQ=売上、VQ=変動費、M=粗利、F=固定費、G=利益" },
  { term: "Tier1 / Tier2", meaning: "物件問合せの段階。Tier1=問合せしてよい候補、Tier2=自動送信の対象" },
  { term: "S1〜S10", meaning: "Grok のAI社員番号。S1物件調査・S2業者開拓・S3需給・S4修繕・S5ペルソナ・S6買付・S7融資・S8ライフライン・S9管理会社・S10周辺マップ" },
  { term: "ジョブ / Mac worker", meaning: "画面のボタンで予約した処理を、Mac 上のプログラムが順に実行する仕組み" },
];

export default function TermGlossary() {
  return (
    <details className="term-glossary">
      <summary>記号・用語の意味</summary>
      <dl>
        {TERMS.map((t) => (
          <div key={t.term} className="term-glossary-row">
            <dt>{t.term}</dt>
            <dd>{t.meaning}</dd>
          </div>
        ))}
      </dl>
      <p className="meta" style={{ margin: "8px 0 0" }}>
        画面の構成は <a href="/guide">構成ガイド</a> にまとめています。
      </p>
    </details>
  );
}
