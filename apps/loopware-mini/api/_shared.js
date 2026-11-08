'use strict';
// 関数どうしで共有する部品：合言葉の確認、回数制限、本文の読み取り、提供元を切り替えるLLM呼び出し。
// 鍵（APIキー）は環境変数からだけ読み、応答・ログ・エラー文には決して出さない。

const crypto = require('crypto');

const BASE_PROMPT =
  'あなたはSNS（X）の投稿文を書く編集者です。与えられたキーワードについて、日本語の投稿文を3案つくってください。\n\n- 3案は、文体や内容を結構バラバラにする';
const FORMAT_PROMPT =
  '前置きや説明は書かない。キーワードが短くても、聞き返さずに必ず3案を書く。出力はJSONだけ。形は {"posts":["案1","案2","案3"]}';
const RULES_HEAD = 'いま効いているルール（利用者の判断から学んだもの。必ず守る）';

const MSG = {
  method: 'POSTで送ってください',
  notReady: 'ただいま準備中です',
  tooMany: 'しばらくしてからもう一度お試しください',
  badPass: '合言葉が違います',
  tooLarge: '送られた内容が大きすぎます',
  badBody: '送られた内容を読み取れませんでした',
  llm: 'AIの呼び出しに失敗しました。少し待ってからもう一度押してください',
  badOutput: 'うまく作れませんでした。もう一度押してください',
  unexpected: 'うまくいきませんでした。もう一度押してください',
};

const MAX_BODY = 64 * 1024;

const SECURITY_HEADERS = {
  'Content-Security-Policy':
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Cache-Control': 'no-store',
};

function send(res, status, obj) {
  if (res.headersSent || res.writableEnded) return;
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) res.setHeader(k, v);
  res.end(JSON.stringify(obj));
}

function fail(res, status, error) {
  send(res, status, { ok: false, error });
}

// 想定外の例外が出ても、中身は出さずに500を返す。ログには例外の種類だけ。
function safe(handler) {
  return async (req, res) => {
    try {
      await handler(req, res);
    } catch (e) {
      console.error('[api] 想定外の例外', (e && e.name) || typeof e);
      fail(res, 500, MSG.unexpected);
    }
  };
}

// ---- 回数制限（メモリ上の簡易版。インスタンスごとなので完全ではない） ----
const FAIL_WINDOW = 10 * 60 * 1000;
const FAIL_LIMIT = 30;
const IP_WINDOW = 10 * 60 * 1000;
const IP_LIMIT = 120;
const ALL_WINDOW = 60 * 60 * 1000;
const ALL_LIMIT = 6000;

const fails = new Map();
const hits = new Map();
const allHits = [];

function trim(arr, windowMs, now) {
  let i = 0;
  while (i < arr.length && arr[i] <= now - windowMs) i++;
  if (i) arr.splice(0, i);
  return arr;
}
function bucket(map, key) {
  let a = map.get(key);
  if (!a) {
    a = [];
    map.set(key, a);
  }
  return a;
}
function sweep(map, windowMs, now) {
  if (map.size < 2000) return;
  for (const [k, a] of map) {
    trim(a, windowMs, now);
    if (!a.length) map.delete(k);
  }
}

// 回数制限の鍵にする IP。利用者が自由に書けるヘッダーは信じない。
// - Vercel 上：プラットフォームが付ける x-vercel-forwarded-for → x-real-ip → x-forwarded-for の先頭
// - 手元（dev-server）：ヘッダーは見ず、実際の接続元だけを使う
function firstHop(v) {
  return String(Array.isArray(v) ? v[0] : v || '')
    .split(',')[0]
    .trim();
}
function clientIp(req) {
  const socketIp = (req.socket && req.socket.remoteAddress) || '';
  if (process.env.VERCEL) {
    const h = req.headers;
    return (
      firstHop(h['x-vercel-forwarded-for']) ||
      firstHop(h['x-real-ip']) ||
      firstHop(h['x-forwarded-for']) ||
      socketIp ||
      'unknown'
    );
  }
  return socketIp || 'unknown';
}

// 長さが違っても落ちないよう、SHA-256のハッシュ同士を比べる
function sameSecret(a, b) {
  const ha = crypto.createHash('sha256').update(String(a), 'utf8').digest();
  const hb = crypto.createHash('sha256').update(String(b), 'utf8').digest();
  return crypto.timingSafeEqual(ha, hb);
}

function passFromHeader(req) {
  let v = req.headers['x-passcode'];
  if (Array.isArray(v)) v = v[0];
  v = typeof v === 'string' ? v : '';
  // 画面側は日本語の合言葉でも送れるよう encodeURIComponent して送る
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
}

function readStream(req) {
  return new Promise((resolve) => {
    if (req.readableEnded || typeof req.on !== 'function') return resolve('');
    const chunks = [];
    let size = 0;
    let over = false;
    req.on('data', (c) => {
      size += c.length;
      if (size > MAX_BODY) over = true;
      else chunks.push(c);
    });
    req.on('end', () => resolve(over ? null : Buffer.concat(chunks).toString('utf8')));
    req.on('error', () => resolve(''));
  });
}

async function readBody(req) {
  const declared = Number(req.headers['content-length']);
  if (Number.isFinite(declared) && declared > MAX_BODY) return { status: 413 };
  let b;
  try {
    b = req.body; // Vercel では、JSONが壊れているとここで例外になる
  } catch {
    return { status: 400 };
  }
  let raw;
  if (b === undefined) {
    raw = await readStream(req);
    if (raw === null) return { status: 413 };
  } else if (Buffer.isBuffer(b)) {
    raw = b.toString('utf8');
  } else if (typeof b === 'string') {
    raw = b;
  } else if (b && typeof b === 'object') {
    let size;
    try {
      size = Buffer.byteLength(JSON.stringify(b));
    } catch {
      return { status: 400 };
    }
    if (size > MAX_BODY) return { status: 413 };
    return { body: b };
  } else {
    return { status: 400 };
  }
  if (Buffer.byteLength(raw) > MAX_BODY) return { status: 413 };
  try {
    return { body: JSON.parse(raw) };
  } catch {
    return { status: 400 };
  }
}

// 共通の入口。通れば本文（オブジェクト）を返す。通らなければ応答を返して null。
async function guard(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    fail(res, 405, MSG.method);
    return null;
  }
  const pass = process.env.EVENT_PASSCODE;
  if (!pass) {
    fail(res, 503, MSG.notReady);
    return null;
  }
  const now = Date.now();
  const ip = clientIp(req);
  const f = trim(bucket(fails, ip), FAIL_WINDOW, now);
  if (f.length >= FAIL_LIMIT) {
    fail(res, 429, MSG.tooMany);
    return null;
  }
  if (!sameSecret(passFromHeader(req), pass)) {
    f.push(now);
    fail(res, 401, MSG.badPass);
    return null;
  }
  const h = trim(bucket(hits, ip), IP_WINDOW, now);
  trim(allHits, ALL_WINDOW, now);
  if (h.length >= IP_LIMIT || allHits.length >= ALL_LIMIT) {
    fail(res, 429, MSG.tooMany);
    return null;
  }
  h.push(now);
  allHits.push(now);
  sweep(fails, FAIL_WINDOW, now);
  sweep(hits, IP_WINDOW, now);

  const r = await readBody(req);
  if (r.status === 413) {
    fail(res, 413, MSG.tooLarge);
    return null;
  }
  if (r.status || !r.body || typeof r.body !== 'object' || Array.isArray(r.body)) {
    fail(res, 400, MSG.badBody);
    return null;
  }
  return r.body;
}

// ---- 入力の整え ----
function cut(v, max) {
  return typeof v === 'string' ? Array.from(v).slice(0, max).join('') : '';
}
function sanitizeRules(v) {
  if (!Array.isArray(v)) return [];
  return v
    .filter((x) => typeof x === 'string')
    .map((x) => cut(x.trim(), 120))
    .filter(Boolean)
    .slice(0, 8);
}
// 応答の最初の { から最後の } までを JSON として読む
function extractJSON(text) {
  if (typeof text !== 'string') return null;
  const i = text.indexOf('{');
  const j = text.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try {
    return JSON.parse(text.slice(i, j + 1));
  } catch {
    return null;
  }
}

// ---- LLMの呼び出し ----
const PROVIDERS = ['anthropic', 'openai', 'openrouter', 'mock'];
const DEFAULT_MODELS = {
  anthropic: { generate: 'claude-haiku-5-5', improve: 'claude-sonnet-5-5' },
};

class LLMError extends Error {
  constructor(kind, status) {
    super('llm ' + kind); // 鍵・本文・提供元の生の応答は入れない
    this.name = 'LLMError';
    this.kind = kind;
    this.status = status || 0;
  }
}

// prefix は '' （主）か 'FALLBACK_'（予備）
function readConfig(prefix, task) {
  const env = process.env;
  const rawProvider = prefix ? env.LLM_FALLBACK_PROVIDER : env.LLM_PROVIDER;
  const provider = String(rawProvider || (prefix ? '' : 'anthropic')).trim().toLowerCase();
  if (!provider) return null;
  if (!PROVIDERS.includes(provider)) return { error: true };
  let key = prefix ? env.LLM_FALLBACK_API_KEY : env.LLM_API_KEY;
  if (!prefix && !key && provider === 'anthropic') key = env.ANTHROPIC_API_KEY;
  key = key ? String(key).trim() : '';
  if (provider !== 'mock' && !key) return { error: true };
  const modelEnv = String(
    (task === 'generate' ? env[`LLM_${prefix}MODEL_GENERATE`] : env[`LLM_${prefix}MODEL_IMPROVE`]) || ''
  ).trim();
  const model = modelEnv || (DEFAULT_MODELS[provider] || {})[task] || (provider === 'mock' ? 'mock' : '');
  if (!model) return { error: true };
  const isDefaultModel = provider === 'anthropic' && model === DEFAULT_MODELS.anthropic[task];
  return { provider, key, model, isDefaultModel };
}

async function callProvider(cfg, task, system, user, maxTokens, timeoutMs) {
  if (cfg.provider === 'mock') {
    const out = mockReply(task, user);
    console.log(`[llm] mock mock in=0 out=0`);
    return out;
  }
  let url;
  let headers;
  let body;
  if (cfg.provider === 'anthropic') {
    url = 'https://api.anthropic.com/v1/messages';
    headers = {
      'x-api-key': cfg.key,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    };
    body = { model: cfg.model, max_tokens: maxTokens, system, messages: [{ role: 'user', content: user }] };
    if (cfg.isDefaultModel) {
      if (task === 'generate') {
        body.thinking = { type: 'disabled' };
        body.output_config = { effort: 'low' };
      } else {
        body.output_config = { effort: 'low' };
      }
    }
  } else {
    url =
      cfg.provider === 'openai'
        ? 'https://api.openai.com/v1/chat/completions'
        : 'https://openrouter.ai/api/v1/chat/completions';
    headers = { Authorization: `Bearer ${cfg.key}`, 'content-type': 'application/json' };
    body = {
      model: cfg.model,
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user },
      ],
    };
    if (cfg.provider === 'openai') {
      body.max_completion_tokens = maxTokens;
    } else {
      body.max_tokens = maxTokens;
      body.reasoning = { enabled: false };
    }
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let data;
  try {
    let r;
    try {
      r = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body), signal: ctrl.signal });
    } catch {
      throw new LLMError(ctrl.signal.aborted ? 'timeout' : 'network');
    }
    if (!r.ok) {
      console.warn(`[llm] ${cfg.provider} status=${r.status}`);
      try {
        await r.text();
      } catch {}
      throw new LLMError('http', r.status);
    }
    try {
      data = await r.json();
    } catch {
      throw new LLMError(ctrl.signal.aborted ? 'timeout' : 'parse');
    }
  } finally {
    clearTimeout(timer);
  }

  let text = '';
  let usage = { input: 0, output: 0 };
  if (cfg.provider === 'anthropic') {
    const blocks = Array.isArray(data && data.content) ? data.content : [];
    text = blocks
      .filter((b) => b && b.type === 'text' && typeof b.text === 'string')
      .map((b) => b.text)
      .join('');
    const u = (data && data.usage) || {};
    usage = { input: Number(u.input_tokens) || 0, output: Number(u.output_tokens) || 0 };
  } else {
    const c = data && Array.isArray(data.choices) && data.choices[0] && data.choices[0].message;
    text = c && typeof c.content === 'string' ? c.content : '';
    const u = (data && data.usage) || {};
    usage = { input: Number(u.prompt_tokens) || 0, output: Number(u.completion_tokens) || 0 };
  }
  console.log(`[llm] ${cfg.provider} ${cfg.model} in=${usage.input} out=${usage.output}`);
  return { text, usage };
}

let primarySkipUntil = 0;

async function callLLM({ task, system, user, maxTokens }) {
  const primary = readConfig('', task);
  const fallback = readConfig('FALLBACK_', task);
  const primaryOk = !!primary && !primary.error;
  const fallbackOk = !!fallback && !fallback.error;
  if (!primaryOk) console.warn('[llm] 設定が足りない');
  if (fallback && fallback.error) console.warn('[llm] 予備の設定が足りない');
  if (!primaryOk && !fallbackOk) throw new LLMError('config');

  if (fallbackOk) {
    if (primaryOk && Date.now() >= primarySkipUntil) {
      try {
        return await callProvider(primary, task, system, user, maxTokens, task === 'generate' ? 10000 : 20000);
      } catch {
        primarySkipUntil = Date.now() + 60000;
        console.warn('[llm] 主が失敗したので予備へ回します');
      }
    }
    return await callProvider(fallback, task, system, user, maxTokens, 25000);
  }
  return await callProvider(primary, task, system, user, maxTokens, 25000);
}

// ---- ダミー出力（LLM_PROVIDER=mock） ----
const MOCK_NOTE = '（ダミー出力。本物のAIは読んでいません）';
const MOCK_RULES = [
  { text: 'です・ます調をやめ、話し言葉の短い文で書く', category: 'style' },
  { text: '自分の体験として、具体的な場面を1つ入れる', category: 'content' },
  { text: '本文は80〜120文字に収める', category: 'format' },
  { text: '1文目は問いかけで始める', category: 'style' },
  { text: '数字（時間・回数・金額など）を1つ入れる', category: 'content' },
  { text: 'ハッシュタグは末尾に2つまでにする', category: 'format' },
  { text: '絵文字は1案につき1つまでにする', category: 'style' },
  { text: '読んだ人が今日試せる行動を1つ入れる', category: 'content' },
  { text: '改行を1〜2回入れて、まとまりを分ける', category: 'format' },
  { text: '語尾に「！」を続けて使わない', category: 'style' },
  { text: 'よくある一般論だけで終わらせない', category: 'content' },
  { text: '最後の1文は短く言い切る', category: 'format' },
];

function mockReply(task, user) {
  const text = String(user || '');
  if (task === 'generate') {
    const kw = cut(text.trim(), 40) || 'キーワード';
    const posts = [
      `【ダミー出力】「${kw}」について、具体的な数字を入れた案です。たとえば「朝の15分で3つ片づけた」のように、場面が浮かぶ書き方にします。本物のAIは呼んでいません。`,
      `【ダミー出力】「${kw}」を問いかけで始める案です。あなたなら、どう始めますか？短い文でテンポよく並べて、最後は一言で言い切ります。本物のAIは呼んでいません。`,
      `【ダミー出力】「${kw}」を体験談ふうにまとめた案です。最初はうまくいかなかったけれど、続けるうちに少しずつ変わってきた、という流れにします。本物のAIは呼んでいません。`,
    ];
    return { text: JSON.stringify({ posts }), usage: { input: 0, output: 0 } };
  }
  // improve：いま効いているルールに無いものを、上から3つ
  const ns = [];
  for (const m of text.matchAll(/^第(\d+)回/gm)) ns.push(Number(m[1]));
  const last = ns.slice(-3);
  const a = last[0] || 1;
  const b = last[1] || a;
  const c = last[2] || b;
  const evidences = [
    `第${a}〜${c}回の案1・案2に共通${MOCK_NOTE}`,
    `第${b}回の案3・第${c}回の案1${MOCK_NOTE}`,
    `第${a}回の案2、理由タグ「長い」${MOCK_NOTE}`,
  ];
  const ruleSection = text.split('いま効いているルール：')[1] || '';
  const picked = MOCK_RULES.filter((r) => !ruleSection.includes(r.text)).slice(0, 3);
  const rules = picked.map((r, i) => ({ ...r, evidence: evidences[i] }));
  const summary =
    '（ダミー出力）判断のログから、書き方・内容・長さの3つの学びを見つけました。本物のAIは読んでいません。';
  return { text: JSON.stringify({ summary, rules }), usage: { input: 0, output: 0 } };
}

module.exports = {
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
  SECURITY_HEADERS,
  MAX_BODY,
};
