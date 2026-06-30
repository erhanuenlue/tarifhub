import { createHash } from "node:crypto";

import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import type { ReviewDecision, ReviewResult } from "@/lib/api";
import { problem, problemFromZod, upstreamProblem } from "@/lib/problem";
import { findReviewItem, REVIEW_QUEUE } from "@/lib/review-fixtures";

const QUEUE_INSTANCE = "/api/review/queue";
const REVIEW_INSTANCE = "/api/review";

/**
 * The console's ONE write path. The review form GETs the queue here and POSTs an
 * approve/correct decision here; the freeze happens server-side. This handler never
 * touches a database and never calls freeze() directly.
 *
 * Two modes, never mixed:
 *   - INGEST_BASE_URL set  -> proxy to the ingestion review endpoint; surface its failures
 *     (a configured backend erroring is a real failure, never masked as success).
 *   - INGEST_BASE_URL unset -> offline demo: serve the fixture queue and simulate the
 *     server-side freeze (a real SHA-256 over the decided content).
 *
 * The ingestion review endpoint is implemented (GET /review/queue, POST /review in
 * services/ingestion/src/tarifhub_ingest/review.py + main.py); it runs the same
 * deterministic validate -> freeze -> audit pipeline as ingest and persists an immutable
 * new version (ADR-013 update). Set INGEST_BASE_URL to proxy to it; the console contract
 * (the types below) is identical in both modes.
 */

// Billing values are frozen at ingest and are never AI-filled or human-corrected here.
// Enforced server-side as defence in depth (the UI also hides them from the editor).
const BILLING_FIELDS = new Set(["tax_points", "price_chf"]);

// The canonical TariffSystem set (mirrors @/lib/api). A review decision always names a real
// frozen system, so the body is validated against this closed set.
const TARIFF_SYSTEMS = ["TARDOC", "EAL", "SL", "MiGeL", "SwissDRG", "TARPSY", "ST_REHA"] as const;

/**
 * Runtime schema for an approve/correct decision, the console's one write path. This replaces
 * the hand-rolled presence and action checks; the billing-field rejection below stays an
 * explicit guard because it is the inviolable-boundary defence, not a shape check.
 */
const ReviewDecisionBody = z.object({
  tariff_system: z.enum(TARIFF_SYSTEMS, { error: "tariff_system is required and must be a known system" }),
  tariff_code: z.string({ error: "tariff_code is required" }).min(1, "tariff_code is required"),
  // Optional: the ingestion contract defaults record_hash to null, so a body that omits it is
  // accepted (normalised to null below), matching the backend and the prior BFF behaviour.
  record_hash: z.string().nullable().optional(),
  action: z.enum(["approve", "correct"], { error: "action must be 'approve' or 'correct'" }),
  corrections: z.record(z.string(), z.string()).optional(),
  reviewer: z.string().optional(),
  note: z.string().optional(),
});
// Unknown keys are stripped by zod (its default), so the proxied decision carries exactly the
// contract above and never forwards arbitrary client fields to the ingestion endpoint.

function ingestBase(): string | null {
  const url = process.env.INGEST_BASE_URL?.trim();
  return url ? url.replace(/\/+$/, "") : null;
}

export async function GET() {
  const base = ingestBase();
  if (!base) return NextResponse.json(REVIEW_QUEUE);
  try {
    const res = await fetch(`${base}/review/queue`, {
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      return upstreamProblem({
        status: res.status,
        body,
        instance: QUEUE_INSTANCE,
        fallbackDetail: `ingestion review queue -> ${res.status}`,
      });
    }
    return NextResponse.json(body);
  } catch (err) {
    return problem({
      status: 502,
      detail: `ingestion review endpoint unreachable: ${String((err as Error).message)}`,
      instance: QUEUE_INSTANCE,
    });
  }
}

export async function POST(req: NextRequest) {
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return problem({ status: 400, detail: "invalid JSON body", instance: REVIEW_INSTANCE });
  }
  const parsed = ReviewDecisionBody.safeParse(raw);
  if (!parsed.success) {
    return problemFromZod(parsed.error, REVIEW_INSTANCE);
  }
  // Normalise an omitted record_hash to null so the decision matches the ReviewDecision
  // contract and the ingestion default (record_hash is Optional[str] = None upstream).
  const decision: ReviewDecision = { ...parsed.data, record_hash: parsed.data.record_hash ?? null };

  // The inviolable boundary, enforced server-side: a billing value is never corrected here.
  if (decision.action === "correct" && decision.corrections) {
    const offending = Object.keys(decision.corrections).filter((k) => BILLING_FIELDS.has(k));
    if (offending.length > 0) {
      return problem({
        status: 400,
        detail: `billing values cannot be corrected: ${offending.join(", ")}`,
        instance: REVIEW_INSTANCE,
      });
    }
  }

  const base = ingestBase();
  if (!base) return NextResponse.json(simulateFreeze(decision));

  // A configured backend: proxy and surface failures (never mask a write failure as success).
  let res: Response;
  try {
    res = await fetch(`${base}/review`, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(decision),
      cache: "no-store",
    });
  } catch (err) {
    return problem({
      status: 502,
      detail: `ingestion review endpoint unreachable: ${String((err as Error).message)}`,
      instance: REVIEW_INSTANCE,
    });
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    return upstreamProblem({
      status: res.status,
      body,
      instance: REVIEW_INSTANCE,
      fallbackDetail: `ingestion review -> ${res.status}`,
    });
  }
  return NextResponse.json(body);
}

/**
 * Stand in for the server-side freeze the ingestion endpoint performs (offline demo only).
 * The new version is prev + 1 and the new record_hash is a genuine SHA-256 over the decided
 * content, so the UI shows a real proposal→frozen transition rather than a fake string. The
 * real ingestion freeze (now implemented) hashes the full canonical record; this demo hash
 * covers only the decision, which is sufficient to make the transition tangible offline.
 */
function simulateFreeze(decision: ReviewDecision): ReviewResult {
  const item = findReviewItem(decision.tariff_system, decision.tariff_code);
  const nextVersion = (item?.version ?? 1) + 1;

  const corrections = decision.action === "correct" ? decision.corrections ?? {} : {};
  const canonical = JSON.stringify({
    system: decision.tariff_system,
    code: decision.tariff_code,
    action: decision.action,
    version: nextVersion,
    corrections: Object.keys(corrections)
      .sort()
      .reduce<Record<string, string>>((acc, k) => ((acc[k] = corrections[k]), acc), {}),
  });
  const recordHash = createHash("sha256").update(canonical).digest("hex");

  const changed = Object.keys(corrections);
  const message =
    decision.action === "approve"
      ? `Approved the ai_map proposal verbatim and froze v${nextVersion}.`
      : changed.length > 0
        ? `Corrected ${changed.join(", ")} and re-froze v${nextVersion}.`
        : `Accepted the proposal and froze v${nextVersion}.`;

  return {
    ok: true,
    tariff_system: decision.tariff_system,
    tariff_code: decision.tariff_code,
    action: decision.action,
    frozen: true,
    version: nextVersion,
    record_hash: recordHash,
    message,
  };
}
