/**
 * 判断デスクから Chatwork へ送る（2026-11-20）。
 * 送り先は名簿 comm_parties.chat_ids に登録されたルームだけ（連絡先一覧.yaml の chatwork_room_id が正本）。
 * 未登録のルームには送らない（誤送信防止。Mac の chatwork_send_once.py と同じ考え方）。
 * 送った文は、日中2時間おきの Chatwork 取込（GHA）が自分の送信として 5.やり取り.md と台帳に入れる。
 */

export type ChatworkRoom = { id: string; name: string };

const NUM = /^\d{5,}$/;

/** chat_ids から登録ルームを取り出す。{id: 名前} と {ラベル: id} の両方の書き方に対応 */
export function roomsFromChatIds(chatIds: unknown): ChatworkRoom[] {
  const c = (chatIds && typeof chatIds === "object" ? chatIds : {}) as Record<string, unknown>;
  const out = new Map<string, string>();
  const rooms = c.chatwork_rooms;
  if (rooms && typeof rooms === "object") {
    for (const [k, v] of Object.entries(rooms as Record<string, unknown>)) {
      const key = String(k).trim();
      const val = String(v ?? "").trim();
      if (NUM.test(key)) out.set(key, val || key);
      else if (NUM.test(val)) out.set(val, key);
    }
  }
  const ids = Array.isArray(c.chatwork_room_id) ? c.chatwork_room_id : c.chatwork_room_id ? [c.chatwork_room_id] : [];
  for (const raw of ids) {
    const id = String(raw).trim();
    if (NUM.test(id) && !out.has(id)) out.set(id, id);
  }
  return [...out.entries()].map(([id, name]) => ({ id, name }));
}

/** 届いたメッセージの「相手から返信（Chatwork・ルーム名）」からルームを推定。1つしかなければそれ */
export function guessRoom(rooms: ChatworkRoom[], channelRaw: string | null | undefined): ChatworkRoom | null {
  const raw = String(channelRaw || "");
  if (raw) {
    const hit = [...rooms].sort((a, b) => b.name.length - a.name.length).find((r) => r.name && raw.includes(r.name));
    if (hit) return hit;
  }
  return rooms.length === 1 ? rooms[0] : null;
}

export function isChatworkRow(row: { channel?: string | null; payload?: Record<string, unknown> | null }): boolean {
  if (/chatwork/i.test(String(row.channel || ""))) return true;
  return /Chatwork/.test(String((row.payload || {}).channel_raw || ""));
}

/** 個人チャットかグループか（送信報告用）。名前に人名だけのものを個人とみなすのは難しいので、登録名で判断 */
export function roomLabel(room: ChatworkRoom): string {
  return `Chatwork「${room.name}」`;
}

export async function postChatworkMessage(
  roomId: string,
  body: string,
  fetchImpl: typeof fetch = fetch,
): Promise<{ ok: true; messageId: string } | { ok: false; error: string }> {
  const token = String(process.env.CHATWORK_API_TOKEN || "").trim();
  if (!token) return { ok: false, error: "CHATWORK_API_TOKEN が Jarvis（Vercel）に設定されていません" };
  if (!NUM.test(roomId)) return { ok: false, error: "room_id が不正です" };
  try {
    const r = await fetchImpl(`https://api.chatwork.com/v2/rooms/${roomId}/messages`, {
      method: "POST",
      headers: { "X-ChatWorkToken": token, "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ body }).toString(),
      cache: "no-store",
    });
    const text = await r.text();
    if (!r.ok) return { ok: false, error: `Chatwork API エラー ${r.status}: ${text.slice(0, 200)}` };
    let id = "";
    try {
      id = String((JSON.parse(text) as { message_id?: string }).message_id || "");
    } catch {
      id = "";
    }
    return { ok: true, messageId: id };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}
