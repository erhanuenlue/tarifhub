/**
 * Demo review queue — the offline contract the console's review form is built against.
 *
 * WHY FIXTURES: these back the offline demo when INGEST_BASE_URL is unset. The ingestion
 * review endpoint is implemented now (GET /review/queue, POST /review); when INGEST_BASE_URL
 * is set the BFF route (app/api/review/route.ts) proxies to it and these fixtures are unused.
 * The items model what the endpoint returns: flagged records (requires_review === true) with
 * the deterministic raw extract beside the ai_map proposal, per field.
 *
 * WHAT AI_MAP ACTUALLY DOES (so the demo never overclaims): ai_map is fill-only for
 * designation.fr / designation.it / category, and only where the source value is absent.
 * Such a field is shown with raw === null and proposal === the AI value (aiFilled: true).
 * Every field the deterministic extract already provides — designation.de, unit, and the
 * billing fields — is shown raw === proposal with aiFilled: false; ai_map never cleans,
 * normalises, or re-authors a value the rules already produced. Billing fields
 * (tax_points / price_chf) are never AI-filled — they appear unchanged and certified. See
 * services/ingestion/src/tarifhub_ingest/mappers/tariff_mapper.py (the AIRefinement schema
 * and the fill-only merge in _claude_assisted_map).
 */
import type { ReviewItem } from "@/lib/api";

// NOTE: `field` keys here (e.g. "designation.de") are the console's contract. They are
// reconciled with the canonical TariffRecord field names in one place,
// services/ingestion/src/tarifhub_ingest/review.py (the corrections map is keyed by them).
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
    flagged_reason: "harmonization_confidence 0.71 < 0.85 — fr/it and category absent in source",
    fields: [
      { field: "designation.de", label: "Designation (DE)", raw: "Hämoglobin A1c (HbA1c)", proposal: "Hämoglobin A1c (HbA1c)", aiFilled: false, billing: false },
      { field: "designation.fr", label: "Designation (FR)", raw: null, proposal: "Hémoglobine A1c (HbA1c)", aiFilled: true, billing: false },
      { field: "designation.it", label: "Designation (IT)", raw: null, proposal: "Emoglobina A1c (HbA1c)", aiFilled: true, billing: false },
      { field: "category", label: "Category", raw: null, proposal: "Klinische Chemie", aiFilled: true, billing: false },
      { field: "unit", label: "Unit", raw: "Bestimmung", proposal: "Bestimmung", aiFilled: false, billing: false },
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
    flagged_reason: "harmonization_confidence 0.83 < 0.85 — fr and category absent in source",
    fields: [
      { field: "designation.de", label: "Designation (DE)", raw: "Dafalgan, Tabletten 500 mg", proposal: "Dafalgan, Tabletten 500 mg", aiFilled: false, billing: false },
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
