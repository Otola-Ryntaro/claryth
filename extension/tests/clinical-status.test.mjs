import assert from "node:assert/strict";
import test from "node:test";

import { clinicalStatusContent, reviewStatusLabel } from "../dist/clinical-status.js";

test("approved and verified data is clearly available", () => {
  const status = clinicalStatusContent(true, true, true);
  assert.equal(status.state, "ready");
  assert.equal(status.label, "判定利用可");
});

test("local data can be shown as a development dataset", () => {
  const status = clinicalStatusContent(true, false, true);
  assert.equal(status.state, "review");
  assert.equal(status.label, "動作確認用DB");
  assert.match(status.message, /実際の判断には使わない/);
});

test("modified local data can still be used for development checks", () => {
  const status = clinicalStatusContent(true, true, false, "database hash mismatch: top20");
  assert.equal(status.state, "review");
  assert.equal(status.label, "動作確認用DB");
  assert.match(status.message, /動作確認として判定できます/);
});

test("expired, invalid, modified, and missing releases have actionable reasons", () => {
  const reasons = [
    ["release manifest has expired", /有効期限/],
    ["release manifest signature is invalid", /電子署名/],
    ["database hash mismatch: top20", /破損または変更/],
    ["release integrity file is missing", /読み込めません/],
  ];
  for (const [reason, expected] of reasons) {
    const status = clinicalStatusContent(true, false, false, reason);
    assert.equal(status.state, "integrity");
    assert.match(status.message, expected);
  }
});

test("offline state blocks interpretation as a data approval state", () => {
  const status = clinicalStatusContent(false, false, false);
  assert.equal(status.state, "offline");
  assert.match(status.title, /接続できません/);
});

test("review status codes are translated for users", () => {
  assert.equal(reviewStatusLabel("clinically_reviewed"), "確認済みデータ");
  assert.equal(
    reviewStatusLabel("pmda_extracted_review_required"),
    "PMDA抽出データ",
  );
  assert.equal(reviewStatusLabel(null), "データ状態がありません");
});
