import test from "node:test";
import assert from "node:assert/strict";
import { mergePrivateContacts } from "../lib/privateContacts.ts";

const base = {
  partners: [
    { name: "運営", folder: "P900_運営", emails: [], phones: [], via_ambiguous: false, emails_private: true },
    { name: "業者", folder: "P100_業者", emails: ["a@example.com"], phones: [], via_ambiguous: false },
  ],
};

test("非公開の宛先を folder で重ねる", () => {
  const got = mergePrivateContacts(base, JSON.stringify({ emails_by_folder: { P900_運営: ["office@example.com"] } }));
  assert.deepEqual(got.partners[0].emails, ["office@example.com"]);
  assert.deepEqual(got.partners[1].emails, ["a@example.com"]);
});

test("未設定・壊れた値は公開分のまま", () => {
  assert.equal(mergePrivateContacts(base, undefined), base);
  assert.equal(mergePrivateContacts(base, "{not json"), base);
  assert.equal(mergePrivateContacts(base, JSON.stringify({ emails_by_folder: { P900_運営: ["no-at"] } })), base);
});

test("同じ宛先は二重にしない", () => {
  const got = mergePrivateContacts(base, JSON.stringify({ emails_by_folder: { P100_業者: ["a@example.com", "b@example.com"] } }));
  assert.deepEqual(got.partners[1].emails, ["a@example.com", "b@example.com"]);
});
