import { test } from 'node:test';
import assert from 'node:assert/strict';
import { needsReview, NEEDS_REVIEW_LABEL } from '../lib/triageStatus.ts';

test('needs_review=true のときだけ要確認', () => {
  assert.equal(needsReview({ needs_review: true }), true);
  assert.equal(needsReview({ needs_review: false }), false);
  assert.equal(needsReview({ needs_review: 'true' }), false);
  assert.equal(needsReview({}), false);
  assert.equal(needsReview(null), false);
  assert.equal(needsReview(undefined), false);
  assert.match(NEEDS_REVIEW_LABEL, /要確認/);
});
