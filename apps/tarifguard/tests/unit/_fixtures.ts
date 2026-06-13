import type { TariffRecord } from "@/lib/api";

/** Build a canonical-shape frozen record for component tests (snake_case, nested designation). */
export function makeRecord(overrides: Partial<TariffRecord> = {}): TariffRecord {
  return {
    tariff_code: "AA.00.0010",
    tariff_system: "TARDOC",
    designation: { de: "Grundkonsultation", fr: null, it: null },
    category: "Grundleistungen",
    tax_points: "9.57",
    price_chf: null,
    unit: null,
    valid_from: "2024-01-01",
    valid_to: null,
    source_url: "https://www.tardoc.example/AA.00.0010",
    source_version: "2024.1",
    harmonization_confidence: 0.95,
    requires_review: false,
    metadata: {},
    record_hash: "a".repeat(64),
    version: 2,
    created_at: "2024-02-15T10:30:00Z",
    ...overrides,
  };
}
