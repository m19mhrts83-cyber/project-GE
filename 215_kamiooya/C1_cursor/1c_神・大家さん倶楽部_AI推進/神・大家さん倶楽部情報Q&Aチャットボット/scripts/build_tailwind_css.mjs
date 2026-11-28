// 画面の Tailwind を、外部の配布元（cdn.tailwindcss.com）から毎回読むのをやめ、style.css の末尾に書き出す（2026-11-28）。
// 版は 3.4.17（それまで CDN が出していた版と同じ）。設定なし（CDN と同じ既定値）。
// 使い方（部品は一時フォルダに入れる。リポには入れない）:
//   npm install --prefix "$TMP/tw" --no-save --ignore-scripts tailwindcss@3.4.17 postcss@8.4.49 autoprefixer@10.4.20
//   NODE_PATH="$TMP/tw/node_modules" node scripts/build_tailwind_css.mjs          # style.css を書き換える
//   NODE_PATH="$TMP/tw/node_modules" node scripts/build_tailwind_css.mjs --check  # 書き出し済みと一致するか（CI）
// index.html・app.js で新しいクラスを使ったら、これを流して style.css も一緒に commit する。
// 置き場所: Raimo は style.css を </head> の直前にもう一度読み込むので、末尾に置くと CDN の時と同じく「最後に効く」順になる。
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const require = createRequire(join(process.env.NODE_PATH || process.cwd(), 'noop.js'));
const tailwindcss = require('tailwindcss');
const postcss = require('postcss');
const autoprefixer = require('autoprefixer');

export const VERSION = '3.4.17';
export const BEGIN = '/* ==== tailwindcss 3.4.17（scripts/build_tailwind_css.mjs が書き出す。手で直さない） ==== */';
export const END = '/* ==== tailwindcss ここまで ==== */';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const content = ['index.html', 'app.js', 'course_catalog.js', 'forum_category_lookup.js'].map(f => join(root, f));

if (require('tailwindcss/package.json').version !== VERSION) throw new Error('tailwindcss は ' + VERSION + ' を使う');
const { css } = await postcss([tailwindcss({ content, corePlugins: {}, plugins: [] }), autoprefixer({ remove: false })])
  .process('@tailwind base;@tailwind components;@tailwind utilities;', { from: undefined });

const stylePath = join(root, 'style.css');
const current = readFileSync(stylePath, 'utf8');
const start = current.indexOf(BEGIN);
const own = (start >= 0 ? current.slice(0, start) : current).replace(/\s*$/, '\n');
const next = own + '\n' + BEGIN + '\n' + css.trim() + '\n' + END + '\n';

if (process.argv.includes('--check')) {
  if (next !== current) { console.error('style.css の Tailwind が古い。scripts/build_tailwind_css.mjs を流して commit する'); process.exit(1); }
  console.log('tailwind: up to date');
} else {
  writeFileSync(stylePath, next);
  console.log('tailwind: written (' + css.length + ' bytes)');
}
