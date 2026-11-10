import assert from "node:assert/strict";
import test from "node:test";
import {
  enqueueDailyReview,
  submitKeyMatches,
  validateDailyReview,
} from "../lib/obsidianReviewInbox.ts";

const valid = {
  review_id: "872d91d4-84c8-4d5d-9b9b-0e8ef76a2be3",
  date: "2026-11-10",
  raw_log: "レビュー記録",
  tactical_review: "次の一手",
};

test("daily review requires a real date, UUID, and both text bodies", () => {
  assert.equal(validateDailyReview(valid).ok, true);
  assert.equal(validateDailyReview({ ...valid, date: "2026-02-30" }).ok, false);
  assert.equal(validateDailyReview({ ...valid, review_id: "not-a-uuid" }).ok, false);
  assert.equal(validateDailyReview({ ...valid, raw_log: " " }).ok, false);
  assert.equal(validateDailyReview({ ...valid, tactical_review: "" }).ok, false);
});

test("submit key uses constant-time equal-length comparison", () => {
  const previous = process.env.TEST_REVIEW_SUBMIT_KEY;
  process.env.TEST_REVIEW_SUBMIT_KEY = "test-secret-value";
  try {
    assert.equal(submitKeyMatches("test-secret-value", "TEST_REVIEW_SUBMIT_KEY"), true);
    assert.equal(submitKeyMatches("wrong-secret", "TEST_REVIEW_SUBMIT_KEY"), false);
    assert.equal(submitKeyMatches("", "TEST_REVIEW_SUBMIT_KEY"), false);
  } finally {
    if (previous === undefined) delete process.env.TEST_REVIEW_SUBMIT_KEY;
    else process.env.TEST_REVIEW_SUBMIT_KEY = previous;
  }
});

test("queue insert is idempotent and does not overwrite a duplicate review id", async () => {
  let inserted;
  const client = {
    from(table) {
      assert.equal(table, "obsidian_review_inbox");
      return {
        insert(row) {
          inserted = row;
          return {
            select() { return this; },
            async maybeSingle() { return { data: { review_id: row.review_id }, error: null }; },
          };
        },
      };
    },
  };
  assert.deepEqual(await enqueueDailyReview(client, { ...valid, date: valid.date }), {
    accepted: true,
    duplicate: false,
  });
  assert.equal(inserted.review_date, valid.date);
  assert.equal(inserted.raw_log, valid.raw_log);

  client.from = () => ({
    insert: () => ({
      select() { return this; },
      async maybeSingle() { return { data: null, error: { code: "23505" } }; },
    }),
  });
  assert.deepEqual(await enqueueDailyReview(client, { ...valid, date: valid.date }), {
    accepted: true,
    duplicate: true,
  });
});
