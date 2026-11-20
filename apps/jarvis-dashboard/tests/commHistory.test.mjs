import assert from "node:assert/strict";
import test from "node:test";
import {
  cleanBody,
  formatHistoryBlock,
  matchPartyIds,
  normFolder,
  summarizeByParty,
} from "../lib/commHistory.ts";

const parties = [
  { party_id: "partner:102_ミニテック", name: "ミニテック", partner_folder: "102_ミニテック" },
  { party_id: "partner:P102_ミニテック", name: "ミニテック", partner_folder: "P102_ミニテック", emails: ["a@mini.example"], email_domains: ["mini.example"] },
  { party_id: "partner:P104_LEAF", name: "LEAF", partner_folder: "P104_LEAF", emails: [], email_domains: ["leaf.example"] },
];

test("フォルダは先頭の P の有無を同じに扱い、同名の2行をまとめて返す", () => {
  assert.equal(normFolder("P806_神大家AI推進"), "806_神大家AI推進");
  assert.deepEqual(matchPartyIds(parties, { folder: "102_ミニテック" }).sort(), ["partner:102_ミニテック", "partner:P102_ミニテック"]);
});

test("フォルダが無ければメール→名前→ドメインの順で探し、見つからなければ空", () => {
  assert.equal(matchPartyIds(parties, { email: "A@mini.example" }).length, 2);
  assert.deepEqual(matchPartyIds(parties, { partner: "LEAF" }), ["partner:P104_LEAF"]);
  assert.deepEqual(matchPartyIds(parties, { email: "x@leaf.example" }), ["partner:P104_LEAF"]);
  assert.deepEqual(matchPartyIds(parties, { partner: "知らない会社" }), []);
});

test("本文から md の折りたたみと Chatwork の引用を外す", () => {
  const raw = "<details>\n<summary>本文を開く</summary>\n\n松野さん\n[qt][qtmeta aid=1 time=2]前の文[/qt]\nありがとうございます。\n</details>";
  assert.equal(cleanBody(raw), "松野さん\n\nありがとうございます。");
});

const item = (id, at, direction, body, channel = "chatwork") => ({
  id, party_id: "partner:P102_ミニテック", channel, direction, occurred_at: at, body_text: body,
});

test("下書きの背景は古い順に並べ、直近に出た自分の文面は参考欄で繰り返さない", () => {
  const recent = [item("2", "2026-11-18T10:00:00Z", "inbound", "新しい"), item("1", "2026-11-17T10:00:00Z", "outbound", "古い自分")];
  const mine = [item("1", "2026-11-17T10:00:00Z", "outbound", "古い自分"), item("0", "2026-11-01T00:00:00Z", "outbound", "前の言い回し", "gmail")];
  const b = formatHistoryBlock("ミニテック", recent, mine);
  assert.ok(b.indexOf("古い自分") < b.indexOf("新しい"));
  assert.match(b, /2026\/11\/18 19:00｜Chatwork｜相手→自分/);
  assert.equal(b.split("古い自分").length - 1, 1);
  assert.match(b, /送った文面[\s\S]*前の言い回し/);
  assert.equal(formatHistoryBlock("x", [], []), "");
});

test("長すぎるときは古いやり取りから落とし、上限を超えない", () => {
  const recent = Array.from({ length: 12 }, (_, i) => item(`r${i}`, `2026-11-${String(18 - i).padStart(2, "0")}T00:00:00Z`, "inbound", `本文${i} ` + "あ".repeat(380)));
  const b = formatHistoryBlock("ミニテック", recent, [], { maxChars: 2000 });
  assert.ok(b.length <= 2000);
  assert.match(b, /本文0 /); // いちばん新しいものは残る
  assert.doesNotMatch(b, /本文11 /);
});

test("相手ごとにまとめて最後にやり取りした順、30日以内の件数も数える", () => {
  const now = new Date("2026-11-20T00:00:00Z");
  const items = [
    { ...item("a", "2026-11-18T00:00:00Z", "inbound", ""), party_id: "partner:P104_LEAF" },
    item("b", "2026-11-10T00:00:00Z", "inbound", ""),
    { ...item("c", "2026-09-01T00:00:00Z", "outbound", ""), party_id: "partner:102_ミニテック" },
  ];
  const s = summarizeByParty(parties, items, now, 3);
  assert.deepEqual(s.map((x) => x.name), ["LEAF", "ミニテック"]);
  assert.equal(s[1].total, 2);
  assert.equal(s[1].last30, 1);
  assert.equal(s[1].folder, "P102_ミニテック");
});
