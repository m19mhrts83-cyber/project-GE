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

test("電話も folder で重ねる", () => {
  const got = mergePrivateContacts(base, JSON.stringify({ phones_by_folder: { P100_業者: ["000-0000-0000"] } }));
  assert.deepEqual(got.partners[1].phones, ["000-0000-0000"]);
  assert.deepEqual(got.partners[0].phones, []);
});

test("公開側に無い取引先は extra_partners で足せる（連絡先は by_folder から）", () => {
  const got = mergePrivateContacts(
    base,
    JSON.stringify({
      extra_partners: [{ name: "新規", folder: "P999_新規" }, { name: "運営", folder: "P900_運営" }],
      emails_by_folder: { P999_新規: ["n@example.com"] },
    }),
  );
  assert.equal(got.partners.length, 3);
  assert.equal(got.partners[2].folder, "P999_新規");
  assert.deepEqual(got.partners[2].emails, ["n@example.com"]);
});
