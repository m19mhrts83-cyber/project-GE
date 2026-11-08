'use strict';
// 手元で動かす用の小さなサーバー（外部パッケージなし）。
// 127.0.0.1 だけで待ち受けるので、同じネットワークの他の端末からは開けません。
// 起動時に .env.local を読みます（値は表示しません。すでにある環境変数は上書きしません）。

const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PUBLIC = path.join(ROOT, 'public');

function loadEnvFile(file) {
  let txt;
  try {
    txt = fs.readFileSync(file, 'utf8');
  } catch {
    return false;
  }
  txt = txt.replace(/^﻿/, '');
  for (const line of txt.split(/\r?\n/)) {
    const m = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!m) continue;
    let v = m[2];
    if (v.length >= 2 && ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'")))) {
      v = v.slice(1, -1);
    }
    if (process.env[m[1]] === undefined) process.env[m[1]] = v;
  }
  return true;
}

const envLoaded = loadEnvFile(path.join(ROOT, '.env.local'));

const { SECURITY_HEADERS, MAX_BODY } = require('./api/_shared');
const handlers = {
  '/api/generate': require('./api/generate'),
  '/api/improve': require('./api/improve'),
};

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
};

function setSecurity(res) {
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) res.setHeader(k, v);
}

function readBodyInto(req) {
  return new Promise((resolve) => {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => {
      size += c.length;
      if (size <= MAX_BODY) chunks.push(c);
    });
    req.on('end', () => {
      if (size > MAX_BODY) {
        req.body = ' '.repeat(MAX_BODY + 1); // 大きすぎる印（_shared の guard が 413 を返す）
      } else {
        const raw = Buffer.concat(chunks).toString('utf8');
        try {
          req.body = JSON.parse(raw);
        } catch {
          req.body = raw; // JSONでないものはそのまま渡す（guard が 400 を返す）
        }
      }
      resolve();
    });
    req.on('error', () => {
      req.body = '';
      resolve();
    });
  });
}

const server = http.createServer(async (req, res) => {
  let pathname = '/';
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
  } catch {
    res.statusCode = 400;
    res.end('Bad Request');
    return;
  }

  const handler = handlers[pathname];
  if (handler) {
    if (req.method === 'POST') await readBodyInto(req);
    await handler(req, res);
    return;
  }

  setSecurity(res);
  if (pathname.startsWith('/api/')) {
    res.statusCode = 404;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ ok: false, error: '見つかりませんでした' }));
    return;
  }
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.statusCode = 405;
    res.end('Method Not Allowed');
    return;
  }

  if (pathname.endsWith('/')) pathname += 'index.html';
  const file = path.normalize(path.join(PUBLIC, pathname));
  if (!file.startsWith(PUBLIC + path.sep)) {
    res.statusCode = 403;
    res.end('Forbidden');
    return;
  }
  fs.readFile(file, (err, data) => {
    if (err) {
      res.statusCode = 404;
      res.setHeader('Content-Type', 'text/plain; charset=utf-8');
      res.end('見つかりませんでした');
      return;
    }
    res.statusCode = 200;
    res.setHeader('Content-Type', TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream');
    res.end(req.method === 'HEAD' ? undefined : data);
  });
});

const port = Number(process.env.PORT) || 3000;
server.on('error', (e) => {
  if (e && e.code === 'EADDRINUSE') {
    console.error(`ポート${port}は、ほかのものが使っています。SETUP.md の「困ったとき」の1を見てください。`);
  } else {
    console.error('サーバーを起動できませんでした。', (e && e.code) || '');
  }
  process.exit(1);
});
server.listen(port, '127.0.0.1', () => {
  const provider = String(process.env.LLM_PROVIDER || 'anthropic').trim().toLowerCase();
  const hasKey = !!(process.env.LLM_API_KEY || (provider === 'anthropic' && process.env.ANTHROPIC_API_KEY));
  console.log('');
  console.log('SNS投稿文ミニループウェア を起動しました');
  console.log(`  ブラウザで開く : http://127.0.0.1:${port}`);
  console.log(`  .env.local     : ${envLoaded ? '読み込みました' : '見つかりません（SETUP.md の手順2）'}`);
  console.log(`  合言葉         : ${process.env.EVENT_PASSCODE ? '設定済み' : '未設定（SETUP.md の手順2）'}`);
  console.log(
    `  AIの提供元     : ${provider === 'mock' ? 'mock（ダミー出力。本物のAIは呼びません）' : provider}` +
      (provider === 'mock' ? '' : `（APIキー：${hasKey ? '設定済み' : '未設定'}）`)
  );
  console.log('  止めるとき     : このウィンドウで Ctrl と C を同時に押す');
  console.log('');
});
