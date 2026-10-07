import assert from "node:assert/strict";
import test from "node:test";
import { composerSkill, hasTableMaterial, runStatusLabel } from "../lib/composer-materials";
import { formatNoticeLine } from "../lib/schedule-notices";

test("removing the last table releases inferred intent for the next prompt", () => {
  assert.equal(composerSkill([{ name: "sales.csv" }], [], "", "weekly_report"), "table_analysis");
  assert.equal(composerSkill([], [], "", "weekly_report"), "weekly_report");
  assert.equal(composerSkill([], ["folder/sales.xlsx"], "", "email_draft"), "table_analysis");
  assert.equal(composerSkill([], [], "", "email_draft"), "email_draft");
});

test("explicit table intent still requires a real CSV or XLSX material", () => {
  assert.equal(composerSkill([], [], "table_analysis", "weekly_report"), "table_analysis");
  assert.equal(hasTableMaterial([{ name: "note.md" }], []), false);
  assert.equal(hasTableMaterial([{ name: "SALES.CSV" }], []), true);
});

test("paused, interrupted and running notices never say completed", () => {
  for (const status of ["paused", "interrupted", "running"]) {
    const line = formatNoticeLine({ run_id: "r", schedule_id: "s", schedule_name: "规则", status });
    assert.ok(line.includes(runStatusLabel(status)));
    assert.ok(!line.includes("已跑完"));
  }
});
