import test from "node:test";
import assert from "node:assert/strict";
import { markTodoistTitle, stripTodoistMark } from "../lib/todoistMark.ts";

test("AI の判断は 🤖、頼まれたら 🦾依頼、本人は印なし", () => {
  assert.equal(markTodoistTitle("[メール要対応][A] 件名"), "🤖 [メール要対応][A] 件名");
  assert.equal(markTodoistTitle("件名", "requested"), "🦾依頼 件名");
  assert.equal(markTodoistTitle(" 件名 ", "none"), "件名");
});

test("印は二重に付けない", () => {
  assert.equal(markTodoistTitle("🤖 件名"), "🤖 件名");
  assert.equal(markTodoistTitle("🦾依頼 件名", "ai"), "🦾依頼 件名");
});

test("比べるときは印を外す", () => {
  assert.equal(stripTodoistMark("🤖 件名"), "件名");
  assert.equal(stripTodoistMark("🦾依頼 件名"), "件名");
  assert.equal(stripTodoistMark("件名"), "件名");
});
