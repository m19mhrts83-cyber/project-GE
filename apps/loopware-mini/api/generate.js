'use strict';
// POST /api/generate  キーワードから投稿文を3案つくる（{"check":true} なら合言葉の確認だけ）

const {
  BASE_PROMPT,
  FORMAT_PROMPT,
  RULES_HEAD,
  MSG,
  send,
  fail,
  safe,
  guard,
  cut,
  sanitizeRules,
  extractJSON,
  callLLM,
} = require('./_shared');

module.exports = safe(async (req, res) => {
  const body = await guard(req, res);
  if (!body) return;

  if (body.check === true) {
    send(res, 200, { ok: true, base: BASE_PROMPT });
    return;
  }

  const keyword = typeof body.keyword === 'string' ? body.keyword.trim() : '';
  const len = Array.from(keyword).length;
  if (len < 1 || len > 40) {
    fail(res, 400, 'キーワードは1〜40文字で入力してください');
    return;
  }
  const rules = sanitizeRules(body.rules);

  const parts = [BASE_PROMPT];
  if (rules.length) parts.push(RULES_HEAD + '\n' + rules.map((r) => '- ' + r).join('\n'));
  parts.push(FORMAT_PROMPT);
  const system = parts.join('\n\n');

  let out;
  try {
    out = await callLLM({ task: 'generate', system, user: keyword, maxTokens: 900 });
  } catch {
    fail(res, 502, MSG.llm);
    return;
  }

  const j = extractJSON(out.text);
  const raw = j && Array.isArray(j.posts) ? j.posts.slice(0, 3) : [];
  const ok = raw.length === 3 && raw.every((p) => typeof p === 'string' && p.trim());
  if (!ok) {
    fail(res, 502, MSG.badOutput);
    return;
  }
  const posts = raw.map((p) => cut(p.trim(), 300));
  send(res, 200, { ok: true, posts, base: BASE_PROMPT, usage: out.usage });
});
