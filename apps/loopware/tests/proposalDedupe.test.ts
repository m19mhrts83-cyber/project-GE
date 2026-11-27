import { test } from "node:test";
import assert from "node:assert/strict";
import {
  candidateKey,
  dropDecided,
  mergeCandidates,
  normSnippet,
  proposalTopicText,
  stableId,
  topicTextsOf,
} from "../lib/proposalDedupe.ts";

const A = { source: "yoritoori", folder: "P312_Newtus", snippet: "・入居者退去の際に経年以外の費用で保険適用できる特約あれば紹介してください", hypothesis: "h" };
const B = { source: "yoritoori", folder: "P205_立木", snippet: "退去ピーク後なので、問題無いと思いますので是非、現状回復やらせてください🙇", hypothesis: "h" };
const J1 = { source: "obsidian_journal", folder: "2026-11-12.md", snippet: "• Pokémon Sleepの記録（※いびきの記録ができていないので要対応）", hypothesis: "j" };
const J2 = { ...J1, folder: "2026-11-13.md" };

test("id は並び順ではなく中身で決まる", () => {
  const x = mergeCandidates([A, B]);
  const y = mergeCandidates([B, A]);
  assert.equal(x.find((c) => c.folder === "P312_Newtus")!.id, y.find((c) => c.folder === "P312_Newtus")!.id);
  assert.notEqual(x[0].id, x[1].id);
  assert.match(stableId("k"), /^miss-[0-9a-z]+$/);
});

test("Journal の同じ行は日付違いでも1枚にまとめる", () => {
  const m = mergeCandidates([J1, J2, A]);
  assert.equal(m.length, 2);
  assert.equal(m[0].merged, 2);
  assert.equal(m[0].folder, "2026-11-12.md・2026-11-13.md");
});

test("やり取りはフォルダが違えば別の案件", () => {
  assert.notEqual(candidateKey(A), candidateKey({ ...A, folder: "P999_別社" }));
});

test("空白・全角半角・先頭の記号の違いは同じとみなす", () => {
  assert.equal(normSnippet("・ 見積を ご確認ください。"), normSnippet("見積をご確認ください"));
  assert.equal(mergeCandidates([A, { ...A, snippet: "入居者退去の際に経年以外の費用で保険適用できる特約あれば紹介してください" }]).length, 1);
});

test("前に採る・見送るを決めたものは外し、保留は前回保留として残す", () => {
  const m = mergeCandidates([A, B, J1]);
  const past = new Map<string, string>([
    [proposalTopicText(A.source, A.snippet), "skip"],
    [proposalTopicText(J1.source, J1.snippet), "hold"],
  ]);
  const { candidates, excluded } = dropDecided(m, past);
  assert.equal(excluded, 1);
  assert.deepEqual(candidates.map((c) => c.folder), ["P205_立木", "2026-11-12.md"]);
  assert.equal(candidates[1].lastChoice, "hold");
  assert.equal(candidates[0].lastChoice, undefined);
  assert.equal("variants" in candidates[0], false);
});

test("topic_text は ProposeClient の保存と同じ形（過去の判断と突き合わせられる）", () => {
  // ProposeClient: `[提案:${source}] ${sourceText}\n→ ${taskTitle}`、taskTitle = snippet.slice(0, 40)
  assert.equal(proposalTopicText("yoritoori", B.snippet), `[提案:yoritoori] ${B.snippet}\n→ ${B.snippet.slice(0, 40)}`);
  assert.equal(topicTextsOf(mergeCandidates([J1, J2])).length, 1);
});
