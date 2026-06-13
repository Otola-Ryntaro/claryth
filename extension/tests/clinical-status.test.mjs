import assert from "node:assert/strict";
import test from "node:test";

import { clinicalStatusContent, reviewStatusLabel } from "../dist/clinical-status.js";

test("approved and verified data is clearly available", () => {
  const status = clinicalStatusContent(true, true, true);
  assert.equal(status.state, "ready");
  assert.equal(status.label, "判定利用可");
});

test("unreviewed data is clearly prohibited", () => {
  const status = clinicalStatusContent(true, false, true);
  assert.equal(status.state, "review");
  assert.equal(status.label, "臨床利用禁止");
  assert.match(status.message, /相互作用判定には使用しない/);
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
  assert.equal(reviewStatusLabel("clinically_reviewed"), "医学レビュー済み");
  assert.equal(
    reviewStatusLabel("pmda_extracted_review_required"),
    "PMDA抽出後・医学レビュー未完了",
  );
  assert.equal(reviewStatusLabel(null), "レビュー情報がありません");
});
