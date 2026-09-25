// Plain Node.js test (node:test + node:assert) for the completeness logic in
// lib/research-progress.ts — deliberately NOT importing the .ts file directly
// (this project has no TypeScript test-runner/loader configured, and adding
// one — ts-node, tsx, Jest, Vitest — would violate the explicit "do not add
// Jest/Vitest or another frontend test framework" instruction). Instead this
// file re-implements the exact same two small pure functions inline, kept in
// sync by hand with lib/research-progress.ts (a deliberate, documented
// duplication of ~15 lines of pure logic, not a new abstraction).
//
// Run with: node --test apps/web/lib/research-progress.test.mjs

import { test } from "node:test";
import assert from "node:assert/strict";

// --- exact copy of the pure logic from lib/research-progress.ts ---
const SECTION_KEYS_WITH_FIELDS = [
  ["question", "summary"],
  ["business", "business_model"],
  ["industry", "competitive_position"],
  ["financials", "financial_snapshot"],
  ["growth", "catalysts"],
  ["management", "management_notes"],
  ["forecast", "assumptions_outlook"],
  ["valuation", "valuation_range"],
  ["scenarios", null], // special-cased below
  ["risks", "risk_register"],
  ["thesis", null],
  ["invalidation", "invalidation_conditions"],
  ["review", null],
];
const TOTAL_SECTIONS = SECTION_KEYS_WITH_FIELDS.length; // 13

function isSectionFilled(item, key, field) {
  if (key === "scenarios") {
    return [item.bull_case, item.base_case, item.bear_case].every(
      (v) => typeof v === "string" && v.trim().length > 0
    );
  }
  if (!field) return false;
  const value = item[field];
  return typeof value === "string" && value.trim().length > 0;
}

function computeProgress(item) {
  const done = SECTION_KEYS_WITH_FIELDS.filter(([key, field]) => isSectionFilled(item, key, field)).length;
  return { done, total: TOTAL_SECTIONS };
}
// --- end copy ---

function emptyResearch(overrides = {}) {
  return {
    summary: "", business_model: "", competitive_position: "", financial_snapshot: "",
    catalysts: "", management_notes: "", assumptions_outlook: "", valuation_range: "",
    bull_case: "", base_case: "", bear_case: "",
    risk_register: "", invalidation_conditions: "",
    ...overrides,
  };
}

test("total is always 13 sections", () => {
  assert.equal(computeProgress(emptyResearch()).total, 13);
});

test("fully empty research has 0 done", () => {
  assert.equal(computeProgress(emptyResearch()).done, 0);
});

test("whitespace-only content does not count as filled", () => {
  const item = emptyResearch({ business_model: "   \n  " });
  assert.equal(computeProgress(item).done, 0);
});

test("one filled text field increments done by exactly 1", () => {
  const item = emptyResearch({ business_model: "Sells enterprise software." });
  assert.equal(computeProgress(item).done, 1);
});

test("scenarios (bull/base/bear) only counts once ALL THREE are filled", () => {
  const partial = emptyResearch({ bull_case: "Upside case", base_case: "Central case" });
  assert.equal(computeProgress(partial).done, 0, "two of three filled must not count yet");

  const complete = emptyResearch({ bull_case: "Upside case", base_case: "Central case", bear_case: "Downside case" });
  assert.equal(computeProgress(complete).done, 1, "all three filled must count as exactly one section");
});

test("management/forecast now bind to real columns (management_notes/assumptions_outlook, added in migration 0007) — filling them counts toward completeness; thesis/review remain derived-only and never count via a same-named key", () => {
  const item = emptyResearch({ management_notes: "Founder-led, high insider ownership.", thesis: "should be ignored" });
  assert.equal(computeProgress(item).done, 1, "management_notes is a real, filled field and must count");

  const stray = emptyResearch({ thesis: "should be ignored", review: "should be ignored" });
  assert.equal(computeProgress(stray).done, 0, "thesis/review have no backing field (derived-only) and must never count");
});

test("all 10 functional non-scenario fields plus scenarios filled = 11 of 13", () => {
  const item = emptyResearch({
    summary: "x", business_model: "x", competitive_position: "x", financial_snapshot: "x",
    catalysts: "x", management_notes: "x", assumptions_outlook: "x", valuation_range: "x",
    bull_case: "x", base_case: "x", bear_case: "x",
    risk_register: "x", invalidation_conditions: "x",
  });
  // 01,02,03,04,05,06,07,08,09(scenarios, counts once),10,12 = 11 sections
  // (11 Investment Thesis and 13 Review are derived-only and never count)
  assert.equal(computeProgress(item).done, 11);
});
