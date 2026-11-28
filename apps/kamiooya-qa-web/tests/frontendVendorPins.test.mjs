import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// 画面の外部部品は版を固定し、改ざん検知（integrity）を付ける。Tailwind は CDN をやめて style.css に書き出す（2026-11-28）。
const dir = new URL('../../../215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/', import.meta.url);
const html = readFileSync(new URL('index.html', dir), 'utf8');
const css = readFileSync(new URL('style.css', dir), 'utf8');

test('Tailwind は外から読まず、style.css の末尾に書き出してある', () => {
  assert.doesNotMatch(html, /cdn\.tailwindcss\.com/);
  assert.match(css, /==== tailwindcss 3\.4\.17[\s\S]*\.flex\s*\{[\s\S]*==== tailwindcss ここまで ==== \*\/\n$/);
});

test('外部の script と stylesheet は版を固定し integrity を付ける（Google Fonts の CSS は中身が変わるので除く）', () => {
  const tags = [...html.matchAll(/<(script|link)\b[^>]*>/g)].map(m => m[0])
    .filter(t => /(src|href)="https?:\/\//.test(t) && (/^<script/.test(t) || /rel="stylesheet"/.test(t)));
  assert.ok(tags.length >= 3);
  for (const tag of tags) {
    const url = tag.match(/(?:src|href)="([^"]+)"/)[1];
    if (url.startsWith('https://fonts.googleapis.com/')) continue;
    assert.match(tag, /integrity="sha(384|512)-[A-Za-z0-9+/=]+"/, url);
    assert.match(tag, /crossorigin="anonymous"/, url);
    assert.match(url, /@\d+\.\d+\.\d+\/|\/\d+\.\d+\.\d+\//, url);
  }
});
