/** グルコン活動／成果報告の Gemini プロンプト */

import type { GluconActiveCycle, GluconExample, GluconJournalDay } from "./types";

function memberHeader(): string {
  const id = (process.env.KAMIOOYA_MEMBER_ID || "").trim();
  const name = (process.env.PERSONAL_NAME || "").trim();
  if (id && name) return `会員番号：${id} ${name}`;
  if (id) return `会員番号：${id}`;
  if (name) return name;
  return "会員番号：（未設定）";
}

export function activityPrompt(args: {
  cycle: GluconActiveCycle;
  journals: GluconJournalDay[];
  examples: GluconExample[];
}): string {
  const monthLabel = args.cycle.periodKey.replace("-", "年") + "月";
  const nextMonth = (() => {
    const [y, m] = args.cycle.periodKey.split("-").map(Number);
    const nm = m === 12 ? 1 : m + 1;
    const ny = m === 12 ? y + 1 : y;
    return `${ny}年${nm}月`;
  })();

  return `あなたは神・大家さん倶楽部の塾生向け「月次活動報告」の下書きライターです。

【厳守】
- 会社の人員計画・社内DX・家庭の雑談など、神大家・不動産投資・融資・物件・空室・修繕・コミュニティ学習・AI推進（神大家関連）以外は書かない。
- 事実のない成果を捏造しない。ジャーナルに無いことは「宣言」側の予定としてだけ書いてよい。
- 出力は投稿本文のみ（前置き・説明・マークダウン見出しの#は不要）。

【形式】コミュニティの定型に合わせる:
■1■今月の活動報告（${monthLabel}度）
・箇条書き（3〜8行）
■2■来月の宣言（${nextMonth}）
・箇条書き（3〜6行）
末尾に短い挨拶1行可。

【提出期限】${args.cycle.reportDeadline}（グルコン ${args.cycle.gluconDate} の10日前）
【Journal 期間】${args.cycle.journalFrom} 〜 ${args.cycle.journalTo}
【会員】${memberHeader()}

【参考例（文体のみ。内容はコピーしない）】
${JSON.stringify(args.examples, null, 2)}

【ジャーナル抜粋（神大家関連）】
${JSON.stringify(
    args.journals.map((j) => ({
      date: j.recorded_at,
      keywords: j.keywords,
      excerpt: j.excerpt,
    })),
    null,
    2,
  )}
`;
}

export function resultPrompt(args: {
  cycle: GluconActiveCycle;
  journals: GluconJournalDay[];
  examples: GluconExample[];
}): string {
  return `あなたは神・大家さん倶楽部の塾生向け「成果報告」の下書きライターです。

【厳守】
- 物件購入・融資実行・空室解消・賃料アップ・修繕コスト削減・管理改善など「実践して成果が出た」ことだけを書く。
- ジャーナルに明確な成果が無い場合は、本文を次の1行だけにする:
  （今月は該当する成果報告なし）
- 会社業務の成果は書かない。捏造禁止。
- 出力は投稿本文のみ。

【推奨形式（成果があるとき）】
■【成果の短い題名】
${memberHeader()}
（可能な範囲でエリア・金額・融資・所感等を箇条書き）
所感等：
・学びと次の一手

【提出期限】${args.cycle.reportDeadline}
【Journal 期間】${args.cycle.journalFrom} 〜 ${args.cycle.journalTo}

【参考例（文体のみ）】
${JSON.stringify(args.examples, null, 2)}

【ジャーナル抜粋】
${JSON.stringify(
    args.journals.map((j) => ({
      date: j.recorded_at,
      keywords: j.keywords,
      excerpt: j.excerpt,
    })),
    null,
    2,
  )}
`;
}
