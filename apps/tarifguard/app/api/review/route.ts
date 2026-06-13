import { createHash } from "node:crypto";

import { NextRequest, NextResponse } from "next/server";

import type { ReviewDecision, ReviewResult } from "@/lib/api";
import { findReviewItem, REVIEW_QUEUE } from "@/lib/review-fixtures";

/**
 * The console's ONE write path. The review form GETs the queue here and POSTs an
 * approve/correct decision here; the freeze happens server-side. This handler never
 * touches a database and never calls freeze() directly.
 *
 * Two modes, never mixed:
 *   - INGEST_BASE_URL set  -> proxy to the ingestion review endpoint; surface its failures
 *     (a configured backend erroring is a real failure, never masked as success).
 *   - INGEST_BASE_URL unset -> offline demo: serve the fixture queue and simulate the
 *     server-side freeze (a real SHA-256 over the decided content). Building the actual
 *     ingestion endpoint is a separate, freeze-line-adjacent task (ADR-013: design scope).
 */

// Billing values are frozen at ingest and are never AI-filled or human-corrected here.
// Enforced server-side as defence in depth (the UI also hides them from the editor).
const BILLING_FIELDS = new Set(["tax_points", "price_chf"]);

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
      return NextResponse.json(body ?? { error: `ingestion review queue -> ${res.status}` }, {
        status: res.status,
      });
    }
    return NextResponse.json(body);
  } catch (err) {
    return NextResponse.json(
      { error: `ingestion review endpoint unreachable: ${String((err as Error).message)}` },
      { status: 502 }
    );
  }
}

export async function POST(req: NextRequest) {
  let decision: ReviewDecision;
  try {
    decision = (await req.json()) as ReviewDecision;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  if (!decision?.tariff_code || !decision?.tariff_system || !decision?.action) {
    return NextResponse.json(
      { error: "decision requires tariff_system, tariff_code and action" },
      { status: 400 }
    );
  }
  if (decision.action !== "approve" && decision.action !== "correct") {
    return NextResponse.json({ error: `unknown action '${decision.action}'` }, { status: 400 });
  }
  // The inviolable boundary, enforced server-side: a billing value is never corrected here.
  if (decision.action === "correct" && decision.corrections) {
    const offending = Object.keys(decision.corrections).filter((k) => BILLING_FIELDS.has(k));
    if (offending.length > 0) {
      return NextResponse.json(
        { error: `billing values cannot be corrected: ${offending.join(", ")}` },
        { status: 400 }
      );
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
    return NextResponse.json(
      { error: `ingestion review endpoint unreachable: ${String((err as Error).message)}` },
      { status: 502 }
    );
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    return NextResponse.json(body ?? { error: `ingestion review -> ${res.status}` }, {
      status: res.status,
    });
  }
  return NextResponse.json(body);
}

/**
 * Stand in for the server-side freeze the future ingestion endpoint will perform (offline
 * demo only). The new version is prev + 1 and the new record_hash is a genuine SHA-256 over
 * the decided content, so the UI shows a real proposal→frozen transition rather than a fake
 * string. (The real ingestion freeze hashes the full canonical record; this demo hash covers
 * only the decision, which is sufficient to make the transition tangible.)
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
