/**
 * Typed, server-side client for the deterministic TarifHub serving API.
 *
 * DETERMINISM BOUNDARY
 * --------------------
 * TarifGuard is a thin READ-ONLY consumer of the serving service. Every value shown
 * in the UI is an unaltered frozen record returned by serving. This client NEVER
 * computes, derives, rounds, or mutates a billing-relevant value (tax_points,
 * price_chf, combinability verdicts) — it only relays what the backend returns.
 *
 * This module reads SERVING_BASE_URL from the environment and therefore runs only on
 * the server (Next.js route handlers in app/api/*). It is never bundled for the
 * browser, so the serving URL stays inside Swiss/EU infrastructure.
 */

export interface TariffRecord {
  id: number;
  tariffCode: string;
  tariffSystem: string;
  designationDe: string | null;
  designationFr: string | null;
  designationIt: string | null;
  category: string | null;
  taxPoints: string | null; // BigDecimal serialized as string — displayed verbatim
  priceChf: string | null; // BigDecimal serialized as string — displayed verbatim
  unit: string | null;
  validFrom: string | null;
  validTo: string | null;
  sourceUrl: string | null;
  sourceVersion: string | null;
  harmonizationConfidence: number;
  requiresReview: boolean;
  recordHash: string;
  version: number;
  createdAt: string;
}

/** One ranked semantic-search hit (mirrors SemanticSearchService.SearchHit). */
export interface SearchHit {
  rank: number;
  record: TariffRecord;
}

/** A single coded position the user pasted into the coding-check screen. */
export interface CodingPosition {
  system: string;
  code: string;
  quantity?: number;
}

/**
 * Deterministic coding-check verdict for one position. All fields are produced by the
 * backend (or by a structural lookup against frozen records); the app adds nothing.
 */
export interface CodingFlag {
  position: CodingPosition;
  found: boolean;
  requiresReview: boolean;
  outsideValidity: boolean;
  /** Backend-owned combinability/validation messages, relayed verbatim. */
  messages: string[];
  record?: TariffRecord;
}

/** De-identified payload accepted by the explanation/cross-walk endpoint. */
export interface ExplainRequest {
  code?: string;
  question?: string;
  /** Already de-identified by lib/deident.ts before it reaches this client. */
  context?: string;
}

export interface ExplainResult {
  code?: string;
  /** Frozen records the explanation is grounded in (values relayed verbatim). */
  records: TariffRecord[];
  /** Natural-language explanation produced by the backend's EU-routed LLM seam. */
  explanation: string | null;
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

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${baseUrl()}${path}`, {
    method: "POST",
    headers: { accept: "application/json", "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ServingError(res.status, `serving POST ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
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

/** Semantic tariff search. Maps to GET /api/v1/search?q=...&limit=...(&system=...). */
export async function searchTariffs(
  query: string,
  opts: { system?: string; limit?: number } = {}
): Promise<SearchHit[]> {
  const params = new URLSearchParams({ q: query });
  if (opts.limit) params.set("limit", String(opts.limit));
  // `system` is an optional filter; serving ignores it until the filter ships, so
  // sending it is forward-compatible and never changes the returned values.
  if (opts.system) params.set("system", opts.system);
  return getJson<SearchHit[]>(`/api/v1/search?${params.toString()}`);
}

/** Fetch one frozen record. Maps to GET /api/v1/tariffs/{system}/{code}. */
export async function getTariff(system: string, code: string): Promise<TariffRecord> {
  return getJson<TariffRecord>(
    `/api/v1/tariffs/${encodeURIComponent(system)}/${encodeURIComponent(code)}`
  );
}

/**
 * Combinability / validation for a set of positions. Maps to the deterministic
 * POST /api/v1/coding-check endpoint owned by serving. The app relays the backend's
 * flags verbatim and computes no verdict of its own. Callers that need a fallback
 * against today's serving build can compose getTariff() per position instead
 * (see app/api/coding-check/route.ts).
 */
export async function checkCoding(positions: CodingPosition[]): Promise<CodingFlag[]> {
  return postJson<CodingFlag[]>("/api/v1/coding-check", { positions });
}

/**
 * Natural-language explanation / TARMED<->TARDOC cross-walk for a position. Maps to
 * the deterministic POST /api/v1/explain endpoint, whose LLM seam runs over frozen
 * records and is routed via AWS Bedrock EU / Google Vertex AI EU. The request body
 * MUST already be de-identified (built by lib/deident.ts).
 */
export async function explain(req: ExplainRequest): Promise<ExplainResult> {
  return postJson<ExplainResult>("/api/v1/explain", req);
}
