/** グルコン活動／成果報告の Gemini プロンプト */

import type {
  GluconActiveCycle,
  GluconExample,
  GluconJournalDay,
  GluconMemberHeaderStatus,
} from "./types";

export type { GluconMemberHeaderStatus };

export function getMemberHeaderStatus(): GluconMemberHeaderStatus {
  const id = (process.env.KAMIOOYA_MEMBER_ID || "").trim();
  const name = (process.env.PERSONAL_NAME || "").trim();
  const missing: string[] = [];
  if (!id) missing.push("KAMIOOYA_MEMBER_ID");
  if (!name) missing.push("PERSONAL_NAME");
  let preview = "会員番号：（未設定）";
  if (id && name) preview = `会員番号：${id} ${name}`;
  else if (id) preview = `会員番号：${id}`;
  else if (name) preview = name;
  return { ok: missing.length === 0, missing, preview };
}

function memberHeader(): string {
  return getMemberHeaderStatus().preview;
}

export function activityPrompt(args: {
  cycle: GluconActiveCycle;
  journals: GluconJournalDay[];
  examples: GluconExample[];
  /** メール・metrics・入退去の月次集約テキスト（任意） */
  monthlyMovesBlock?: string;
}): string {
  const monthLabel = args.cycle.periodKey.replace("-", "年") + "月";
  const nextMonth = (() => {
    const [y, m] = args.cycle.periodKey.split("-").map(Number);
    const nm = m === 12 ? 1 : m + 1;
    const ny = m === 12 ? y + 1 : y;
    return `${ny}年${nm}月`;
  })();

  const moves = args.monthlyMovesBlock?.trim()
    ? `\n${args.monthlyMovesBlock.trim()}\n`
    : "";

  return `あなたは神・大家さん倶楽部の塾生向け「月次活動報告」の下書きライターです。

【厳守】
- 会社の人員計画・社内DX・家庭の雑談など、神大家・不動産投資・融資・物件・空室・修繕・コミュニティ学習・AI推進（神大家関連）以外は書かない。
- 事実のない成果を捏造しない。ジャーナル／今月の動きに無いことは「宣言」側の予定としてだけ書いてよい。
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
${moves}`;
}

export function resultPrompt(args: {
  cycle: GluconActiveCycle;
  journals: GluconJournalDay[];
  examples: GluconExample[];
  /** 神大家ポイント配点基準の要約（formatRubricForPrompt の出力） */
  rubricSummary?: string;
  monthlyMovesBlock?: string;
}): string {
  const rubricBlock = args.rubricSummary?.trim()
    ? `
【神大家ポイント観点（採点者が見る軸。投稿本文に点数・ルールIDは書かない）】
${args.rubricSummary.trim()}
`
    : "";

  const moves = args.monthlyMovesBlock?.trim()
    ? `\n${args.monthlyMovesBlock.trim()}\n`
    : "";

  return `あなたは神・大家さん倶楽部の塾生向け「成果報告」の下書きライターです。

【厳守】
- 物件購入・融資実行・空室解消・賃料アップ・修繕コスト削減・管理改善など「実践して成果が出た」ことだけを書く。
- ジャーナル／今月の動きに明確な成果が無い場合は、本文を次の1行だけにする:
  （今月は該当する成果報告なし）
- Journal／今月の動きにない成果・金額を捏造しない。会社業務の成果は書かない。
- 該当カテゴリが分かる題名／箇条書きにする（購入AP・戸建・空室・修繕・売却・融資・業者・情報・幹事など）。
- 価格・利回り・融資条件・期間・削減額・手順など、採点根拠になる数字・再現情報を、事実がある範囲で必ず書く。
- 投稿本文に「〇点」「ルールID」は書かない。
- 出力は投稿本文のみ。
${rubricBlock}
【推奨形式（成果があるとき）】
■【カテゴリが分かる題名】
${memberHeader()}
・成果の事実（何をいつ）
・数字（金額／利回り／融資／削減額など、分かるもの）
・やったこと・手順（再現できる粒度）
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
${moves}`;
}
