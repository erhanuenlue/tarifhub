/**
 * Demo review queue — the contract the console's review form is built against.
 *
 * WHY FIXTURES: no serving/ingestion endpoint accepts review decisions yet, and the
 * raw-extract-vs-ai_map-proposal pair does not survive freeze (ADR-013: the review POST is
 * design scope at the MVP, not implemented). These items model exactly what a future
 * ingestion review endpoint would return: flagged records (requires_review === true) with
 * the deterministic raw extract beside the ai_map proposal, per field. The BFF route
 * (app/api/review/route.ts) serves these offline and would proxy to that endpoint
 * (INGEST_BASE_URL) once it exists. Billing fields (tax_points / price_chf) are never
 * AI-filled — they appear unchanged and certified.
 */
import type { ReviewItem } from "@/lib/api";

export const REVIEW_QUEUE: ReviewItem[] = [
  {
    tariff_system: "TARDOC",
    tariff_code: "AA.00.0020",
    record_hash: "7f3c91a4e2b8d05c6a1f4e9b2c7d8a0e3f6b1c4d9e8a2b7c0d3f6a9e1b4c7d0e",
    version: 1,
    designation_de: "Konsultation, jede weitere 5 Min.",
    confidence: 0.78,
    requires_review: true,
    ai_model: "claude-opus-4-8",
    flagged_reason: "harmonization_confidence 0.78 < 0.85 — fr/it and category absent in source",
    fields: [
      { field: "designation.de", label: "Designation (DE)", raw: "Konsultation, jede weitere 5 Min.", proposal: "Konsultation, jede weitere 5 Min.", aiFilled: false, billing: false },
      { field: "designation.fr", label: "Designation (FR)", raw: null, proposal: "Consultation, par 5 min supplémentaires", aiFilled: true, billing: false },
      { field: "designation.it", label: "Designation (IT)", raw: null, proposal: "Consultazione, ogni 5 min supplementari", aiFilled: true, billing: false },
      { field: "category", label: "Category", raw: null, proposal: "Grundleistungen", aiFilled: true, billing: false },
      { field: "tax_points", label: "Tax points", raw: "9.57", proposal: "9.57", aiFilled: false, billing: true },
    ],
  },
  {
    tariff_system: "EAL",
    tariff_code: "1771.00",
    record_hash: "b2e8d14f7a3c9061e5b8d2f4a7c1e9b6d3f0a8c5e2b7d4f1a9c6e3b0d7f4a1c8",
    version: 1,
    designation_de: "Hämoglobin A1c (HbA1c)",
    confidence: 0.71,
    requires_review: true,
    ai_model: "claude-opus-4-8",
    flagged_reason: "low confidence 0.71 — noisy source designation normalised by ai_map",
    fields: [
      { field: "designation.de", label: "Designation (DE)", raw: "Haemoglobln A1c  (HbA1 c)", proposal: "Hämoglobin A1c (HbA1c)", aiFilled: true, billing: false },
      { field: "unit", label: "Unit", raw: null, proposal: "Bestimmung", aiFilled: true, billing: false },
      { field: "tax_points", label: "Tax points", raw: "23.00", proposal: "23.00", aiFilled: false, billing: true },
    ],
  },
  {
    tariff_system: "SL",
    tariff_code: "7680565740013",
    record_hash: "c4a1f7b0d3e6928a5c8e1b4d7f0a3c6e9b2d5f8a1c4e7b0d3f6a9c2e5b8d1f4a",
    version: 1,
    designation_de: "Dafalgan, Tabletten 500 mg",
    confidence: 0.83,
    requires_review: true,
    ai_model: "claude-opus-4-8",
    flagged_reason: "confidence 0.83 < 0.85 — fr designation and category proposed by ai_map",
    fields: [
      { field: "designation.de", label: "Designation (DE)", raw: "DAFALGAN cpr 500mg", proposal: "Dafalgan, Tabletten 500 mg", aiFilled: true, billing: false },
      { field: "designation.fr", label: "Designation (FR)", raw: null, proposal: "Dafalgan, comprimés 500 mg", aiFilled: true, billing: false },
      { field: "category", label: "Category", raw: null, proposal: "Analgetika", aiFilled: true, billing: false },
      { field: "price_chf", label: "Price (CHF)", raw: "4.85", proposal: "4.85", aiFilled: false, billing: true },
    ],
  },
];

/** Look up a queued item by its (system, code) key. */
export function findReviewItem(system: string, code: string): ReviewItem | undefined {
  return REVIEW_QUEUE.find(
    (i) => i.tariff_system === system && i.tariff_code === code
  );
}
