'use strict';
// POST /api/improve  判断のログを読んで「次の生成で守るとよいルール」の案をつくる

const { MSG, send, fail, safe, guard, cut, sanitizeRules, extractJSON, callLLM } = require('./_shared');

const SYSTEM = `あなたは、SNS投稿文のプロンプトを育てる分析者です。利用者が3案ずつ受け取って下した判断のログを読み、「次の生成で守るとよいルール」を最大5つ提案してください。

見るところ
- 「良い」とされた案と「悪い」とされた案の共通点
- 利用者が本文を直した箇所（直す前と直した後の差）の傾向
- 理由タグと一言

守ること
- ルールは「〜する」「〜しない」の1文で、生成AIにそのまま渡せる具体的な書き方にする
- 根拠（どの回のどの案か、何回分の判断か）を添える。回と案は、ログの表記どおり「第2回の案1・案3」「第1〜3回」のように書く（画面で、根拠にした判断を光でつなぐのに使う）。1回しか見えない傾向は、根拠に「仮説：1回分のみ」と書く
- いま効いているルールと重複するものは出さない
- 判断が少なく言い切れないときは、無理に5つ出さず、少なくてよい
- 生成AIには最初、「3案は文体や内容を結構バラバラにする」という指示だけが渡されている。長さ・文末・語り口・入れる内容などは、判断から学んで足していく
- 各ルールに分類を付ける：style（文体・語り口・文末）、content（入れる内容・切り口・避ける話題）、format（長さ・文字数・構成などの出力の形）

出力はJSONだけ。形は {"summary":"全体の一言","rules":[{"text":"ルール文","category":"style|content|format","evidence":"根拠"}]}`;

const CATEGORIES = ['style', 'content', 'format'];

function sanitizeRounds(v) {
  if (!Array.isArray(v)) return [];
  return v
    .slice(-10)
    .map((r, i) => {
      if (!r || typeof r !== 'object') return null;
      const n = Number.isInteger(r.n) && r.n > 0 && r.n < 1e7 ? r.n : i + 1;
      const keyword = cut(r.keyword, 40).trim();
      const posts = Array.isArray(r.posts)
        ? r.posts
            .slice(0, 3)
            .map((p) => {
              if (!p || typeof p !== 'object') return null;
              const original = cut(p.original, 300);
              // verdict は文字列の good / bad との厳密な比較だけを通す
              const verdict = p.verdict === 'good' ? 'good' : p.verdict === 'bad' ? 'bad' : null;
              let edited = typeof p.edited === 'string' ? cut(p.edited, 300) : null;
              if (edited !== null && edited === original) edited = null;
              const tags = Array.isArray(p.tags)
                ? p.tags
                    .filter((t) => typeof t === 'string')
                    .map((t) => cut(t.trim(), 10))
                    .filter(Boolean)
                    .slice(0, 5)
                : [];
              const note = cut(p.note, 60).trim();
              return { original, verdict, edited, tags, note };
            })
            .filter(Boolean)
        : [];
      return { n, keyword, posts };
    })
    .filter(Boolean);
}

const judged = (r) => r.posts.some((p) => p.verdict || p.edited !== null);
const oneLine = (s) => String(s).replace(/\s*\r?\n\s*/g, ' ');

function buildUser(rounds, rules) {
  const lines = [];
  for (const r of rounds) {
    lines.push(`第${r.n}回　キーワード：${oneLine(r.keyword)}`);
    r.posts.forEach((p, k) => {
      let l = `案${k + 1}　判定：${p.verdict === 'good' ? '良い' : p.verdict === 'bad' ? '悪い' : '未判定'}`;
      if (p.tags.length) l += `　理由タグ：${p.tags.join('・')}`;
      if (p.note) l += `　一言：${oneLine(p.note)}`;
      lines.push(l);
      lines.push(`　直す前：${oneLine(p.original)}`);
      if (p.edited !== null) lines.push(`　直した後：${oneLine(p.edited)}`);
    });
    lines.push('');
  }
  if (rules.length) lines.push('いま効いているルール：\n' + rules.map((x) => '- ' + x).join('\n'));
  else lines.push('いま効いているルール：なし');
  return lines.join('\n');
}

module.exports = safe(async (req, res) => {
  const body = await guard(req, res);
  if (!body) return;

  const rounds = sanitizeRounds(body.rounds).filter(judged);
  const rules = sanitizeRules(body.rules);
  if (rounds.length < 3) {
    fail(res, 400, '判断が3回分溜まってから使えます');
    return;
  }

  let out;
  try {
    out = await callLLM({ task: 'improve', system: SYSTEM, user: buildUser(rounds, rules), maxTokens: 3000 });
  } catch {
    fail(res, 502, MSG.llm);
    return;
  }

  const j = extractJSON(out.text);
  if (!j || typeof j !== 'object' || !Array.isArray(j.rules)) {
    fail(res, 502, MSG.badOutput);
    return;
  }
  const outRules = j.rules
    .map((x) => {
      if (typeof x === 'string') x = { text: x };
      if (!x || typeof x !== 'object') return null;
      const text = cut(typeof x.text === 'string' ? x.text.trim() : '', 120);
      if (!text) return null;
      const category = CATEGORIES.includes(x.category) ? x.category : 'content';
      const evidence = cut(typeof x.evidence === 'string' ? x.evidence.trim() : '', 200);
      return { text, category, evidence };
    })
    .filter(Boolean)
    .slice(0, 5);
  const summary = cut(typeof j.summary === 'string' ? j.summary.trim() : '', 200);
  send(res, 200, { ok: true, summary, rules: outRules, usage: out.usage });
});
