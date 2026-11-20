import assert from "node:assert/strict";
import test from "node:test";
import { guessRoom, isChatworkRow, postChatworkMessage, roomsFromChatIds } from "../lib/chatworkSend.ts";

test("名簿の2つの書き方（{id:名前} と {ラベル:id}）からルームを取り出す", () => {
  const a = roomsFromChatIds({ chatwork_rooms: { "439357504": "【神大家】松野さん・スクール運営社員", "422374412": "目黒 啓太" }, chatwork_room_id: ["422374412", "439357504"] });
  assert.deepEqual(a.map((r) => r.id).sort(), ["422374412", "439357504"]);
  const b = roomsFromChatIds({ chatwork_rooms: { juku2: "425809560" }, chatwork_room_id: ["425809560", "420522792"] });
  assert.deepEqual(b, [{ id: "425809560", name: "juku2" }, { id: "420522792", name: "420522792" }]);
  assert.deepEqual(roomsFromChatIds(null), []);
});

test("届いたルーム名から送り先を推定し、分からなければ空（1つだけならそれ）", () => {
  const rooms = [{ id: "1111111", name: "目黒 啓太" }, { id: "2222222", name: "【神大家】松野さん・スクール運営社員" }];
  assert.equal(guessRoom(rooms, "相手から返信（Chatwork・【神大家】松野さん・スクール運営社員）")?.id, "2222222");
  assert.equal(guessRoom(rooms, "相手から返信（Chatwork）"), null);
  assert.equal(guessRoom([rooms[0]], "")?.id, "1111111");
});

test("Chatwork の行かどうか", () => {
  assert.equal(isChatworkRow({ channel: "Chatwork" }), true);
  assert.equal(isChatworkRow({ channel: null, payload: { channel_raw: "相手から返信（Chatwork・x）" } }), true);
  assert.equal(isChatworkRow({ channel: "Gmail", payload: {} }), false);
});

test("鍵が無ければ送らない・送ると message_id を返す", async () => {
  delete process.env.CHATWORK_API_TOKEN;
  const no = await postChatworkMessage("1234567", "本文");
  assert.equal(no.ok, false);
  process.env.CHATWORK_API_TOKEN = "t";
  let seen;
  const fake = async (url, init) => {
    seen = { url, init };
    return new Response(JSON.stringify({ message_id: "999" }), { status: 200 });
  };
  const ok = await postChatworkMessage("1234567", "お疲れさまです。", fake);
  assert.deepEqual(ok, { ok: true, messageId: "999" });
  assert.match(seen.url, /rooms\/1234567\/messages$/);
  assert.equal(seen.init.headers["X-ChatWorkToken"], "t");
  assert.equal((await postChatworkMessage("abc", "x", fake)).ok, false);
});
