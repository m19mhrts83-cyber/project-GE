import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// 本番の Raimo に送るのはチャットボットフォルダ側（scripts/kamiooya_qa_release.py --raimo-front）。
// public/raimo だけ直して反映し忘れないよう、app.js と index.html は同じ中身に保つ（2026-11-10）。
const chatbot = new URL('../../../215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/', import.meta.url);
const pub = new URL('../public/raimo/', import.meta.url);
for (const name of ['app.js', 'index.html']) {
  test(`${name} は public/raimo とチャットボットフォルダで同じ`, () => {
    assert.equal(readFileSync(new URL(name, chatbot), 'utf8'), readFileSync(new URL(name, pub), 'utf8'));
  });
}
