/**
 * Typed, server-side client for the deterministic tarifhub serving API (L1 TarifCore).
 *
 * DETERMINISM BOUNDARY
 * --------------------
 * TarifGuard is a thin READ-ONLY consumer of serving. Every value shown in the UI is an
 * unaltered frozen record returned by serving. This client NEVER computes, derives,
 * rounds, or mutates a billing-relevant value (tax_points, price_chf) — it only relays
 * what the backend returns. Money/point fields arrive as decimal STRINGS and are rendered
 * verbatim; they are never parsed into a JS number on the value path.
 *
 * WIRE SHAPE
 * ----------
 * The wire shape is the canonical Pydantic `TariffRecord` end-to-end (one model across the
 * whole platform): snake_case keys and a nested `designation` object. See
 * services/serving/src/tarifhub_serving/main.py and
 * services/ingestion/src/tarifhub_ingest/models/tariff_model.py.
 *
 * This module reads SERVING_BASE_URL from the environment and therefore runs only on the
 * server (Next.js route handlers in app/api/* and async server components). It is never
 * bundled for the browser, so the serving URL stays inside Swiss/EU infrastructure.
 */

export type TariffSystem =
  | "TARDOC"
  | "EAL"
  | "SL"
  | "MiGeL"
  | "SwissDRG"
  | "TARPSY"
  | "ST_REHA";

/** Multilingual designation. German is the canonical reference language. */
export interface Designation {
  de: string;
  fr: string | null;
  it: string | null;
}

/**
 * The canonical frozen tariff record, exactly as serving serialises it. Decimal money/
 * point fields are strings (precision-preserving) and are displayed verbatim.
 */
export interface TariffRecord {
  tariff_code: string;
  tariff_system: TariffSystem;
  designation: Designation;
  category: string | null;
  tax_points: string | null;
  price_chf: string | null;
  unit: string | null;
  valid_from: string | null;
  valid_to: string | null;
  source_url: string | null;
  source_version: string | null;
  harmonization_confidence: number;
  requires_review: boolean;
  metadata: Record<string, unknown>;
  record_hash: string | null;
  version: number;
  created_at: string;
}

/** One ranked semantic-search hit (mirrors serving's SearchHit). */
export interface SearchHit {
  rank: number;
  record: TariffRecord;
}

/** One field that differs between two frozen versions (mirrors serving's FieldChange). */
export interface FieldChange {
  field: string;
  from_value: unknown;
  to_value: unknown;
}

/** Field-level diff between two versions of a frozen record. */
export interface DiffResponse {
  tariff_system: string;
  tariff_code: string;
  from_version: number;
  to_version: number;
  from_record_hash: string | null;
  to_record_hash: string | null;
  changes: FieldChange[];
}

/**
 * Deterministic, record-grounded explanation for a code (serving GET /api/v1/explain).
 * `explanation` is rule-generated and labelled "[deterministic]" by the backend; the
 * console renders it on a labelled .ai-content surface (the explain seam is designed to
 * host an AI explanation; today it is deterministic — the guardrail label stays either way).
 */
export interface ExplainResponse {
  code: string;
  records: TariffRecord[];
  explanation: string;
}

/* -------------------------------------------------------------------------- *
 *  Review contract (console-defined).
 *
 *  The ingestion review endpoint accepts these decisions (GET /review/queue, POST /review).
 *  The deterministic raw-vs-proposal pair is reconstructed server-side from
 *  metadata.ai_fields — an AI-filled field had an empty raw extract (raw === null); the raw
 *  text of a value the AI merely normalised does not survive freeze and is not invented.
 *  These types are the contract the console's review form is built against; the BFF route
 *  app/api/review/route.ts serves the fixture queue offline and proxies to the ingestion
 *  endpoint when INGEST_BASE_URL is set (it freezes server-side). The console itself never
 *  touches the DB and never freezes.
 * -------------------------------------------------------------------------- */

/** One field in the review diff: deterministic raw extract vs the ai_map proposal. */
export interface ReviewField {
  field: string;
  label: string;
  raw: string | null;
  proposal: string | null;
  /** True when ai_map proposed/filled this field (metadata.ai_fields). */
  aiFilled: boolean;
  /** True for tax_points / price_chf — billing values, never AI-filled, shown certified. */
  billing: boolean;
}

/** One flagged record awaiting human review (requires_review === true). */
export interface ReviewItem {
  tariff_system: TariffSystem;
  tariff_code: string;
  record_hash: string | null;
  version: number;
  designation_de: string;
  confidence: number;
  requires_review: boolean;
  ai_model: string | null;
  flagged_reason: string;
  fields: ReviewField[];
}

export type ReviewAction = "approve" | "correct";

/** The human decision the review form POSTs to the BFF (the one write path). */
export interface ReviewDecision {
  tariff_system: TariffSystem;
  tariff_code: string;
  record_hash: string | null;
  action: ReviewAction;
  /** field -> corrected value, when action === "correct". Billing fields are excluded. */
  corrections?: Record<string, string>;
  reviewer?: string;
  note?: string;
}

/** The result of an approve/correct: the (re)frozen record, decided server-side. */
export interface ReviewResult {
  ok: boolean;
  tariff_system: string;
  tariff_code: string;
  action: ReviewAction;
  frozen: boolean;
  version: number;
  record_hash: string;
  message: string;
}

/* -------------------------------------------------------------------------- *
 *  Coding-check contract (console-defined, structural only).
 *
 *  Serving exposes no combinability endpoint, so the coding-check screen reports only
 *  frozen-record facts looked up per position via GET /api/v1/tariffs/{system}/{code}:
 *  whether the code exists, whether it is flagged for review, and whether it falls outside
 *  its validity window. No combinability verdict and no billing value are ever computed here.
 * -------------------------------------------------------------------------- */

/** One coded position the user pasted into the coding-check screen. */
export interface CodingPosition {
  system: string;
  code: string;
}

/** Structural check result for one position — frozen-record facts only. */
export interface CodingFlag {
  position: CodingPosition;
  found: boolean;
  requires_review: boolean;
  outside_validity: boolean;
  record?: TariffRecord;
  messages: string[];
}

/** Raised when the serving API returns a non-2xx status. */
export class ServingError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ServingError";
  }
}

function baseUrl(): string {
  const url = process.env.SERVING_BASE_URL;
  if (!url) {
    throw new Error(
      "SERVING_BASE_URL is not set — point it at the deterministic serving API " +
        "(see apps/tarifguard/.env.example)."
    );
  }
  return url.replace(/\/+$/, "");
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${baseUrl()}${path}`, {
    headers: { accept: "application/json" },
    // Tariff facts are frozen; a short cache is safe and keeps the UI snappy.
    next: { revalidate: 30 },
  });
  if (!res.ok) {
    throw new ServingError(res.status, `serving GET ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

/** Semantic tariff search. Maps to GET /api/v1/search?q=...&limit=... */
export async function searchTariffs(
  query: string,
  opts: { limit?: number } = {}
): Promise<SearchHit[]> {
  const params = new URLSearchParams({ q: query });
  params.set("limit", String(opts.limit ?? 10));
  return getJson<SearchHit[]>(`/api/v1/search?${params.toString()}`);
}

/** Browse the latest version of each frozen record, optionally filtered by system. */
export async function listTariffs(
  opts: { system?: string; limit?: number; offset?: number } = {}
): Promise<TariffRecord[]> {
  const params = new URLSearchParams();
  if (opts.system) params.set("system", opts.system);
  params.set("limit", String(opts.limit ?? 25));
  if (opts.offset) params.set("offset", String(opts.offset));
  return getJson<TariffRecord[]>(`/api/v1/tariffs?${params.toString()}`);
}

/** Fetch one frozen record. Maps to GET /api/v1/tariffs/{system}/{code}. Throws on 404. */
export async function getTariff(system: string, code: string): Promise<TariffRecord> {
  return getJson<TariffRecord>(
    `/api/v1/tariffs/${encodeURIComponent(system)}/${encodeURIComponent(code)}`
  );
}

/**
 * Deterministic, record-grounded explanation for a code. Maps to the GET
 * /api/v1/explain?code=...(&system=...) endpoint. Input is a tariff code only — no
 * free-text, no patient data — so nothing needs de-identification here.
 */
export async function getExplain(
  code: string,
  opts: { system?: string } = {}
): Promise<ExplainResponse> {
  const params = new URLSearchParams({ code });
  if (opts.system) params.set("system", opts.system);
  return getJson<ExplainResponse>(`/api/v1/explain?${params.toString()}`);
}

/** Field-level diff between two frozen versions. Maps to .../{system}/{code}/diff. */
export async function getDiff(
  system: string,
  code: string,
  from: number,
  to: number
): Promise<DiffResponse> {
  return getJson<DiffResponse>(
    `/api/v1/tariffs/${encodeURIComponent(system)}/${encodeURIComponent(code)}/diff?from=${from}&to=${to}`
  );
}

/** Truncate a record_hash for chip display (frozen records carry a full SHA-256). */
export function shortHash(hash: string | null, len = 12): string {
  if (!hash) return "unhashed";
  return hash.length <= len ? hash : `${hash.slice(0, len)}…`;
}

/**
 * Select the record's primary billing value for display — tax_points (TP) for point-based
 * systems, else price_chf (CHF). This is verbatim SELECTION, never computation: it picks
 * one of two strings the backend already froze and attaches its unit label.
 */
export function primaryValue(r: TariffRecord): { value: string | null; unit: string | null } {
  if (r.tax_points !== null && r.tax_points !== undefined) return { value: r.tax_points, unit: "TP" };
  if (r.price_chf !== null && r.price_chf !== undefined) return { value: r.price_chf, unit: "CHF" };
  return { value: null, unit: null };
}
