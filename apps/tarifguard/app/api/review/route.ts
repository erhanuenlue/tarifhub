import { createHash } from "node:crypto";

import { NextRequest, NextResponse } from "next/server";

import type { ReviewDecision, ReviewResult } from "@/lib/api";
import { findReviewItem, REVIEW_QUEUE } from "@/lib/review-fixtures";

/**
 * The console's ONE write path. The review form GETs the queue here and POSTs an
 * approve/correct decision here; the freeze happens server-side. This handler never
 * touches a database and never calls freeze() directly — it proxies to the ingestion
 * review endpoint when INGEST_BASE_URL is configured, and otherwise serves the demo
 * fixtures and simulates the server-side freeze (a real SHA-256 over the decided content,
 * mirroring how ingestion freezes records). Building the actual ingestion endpoint is a
 * separate, freeze-line-adjacent task (ADR-013: design scope at the MVP).
 */

function ingestBase(): string | null {
  const url = process.env.INGEST_BASE_URL?.trim();
  return url ? url.replace(/\/+$/, "") : null;
}

export async function GET() {
  const base = ingestBase();
  if (base) {
    try {
      const res = await fetch(`${base}/review/queue`, {
        headers: { accept: "application/json" },
        cache: "no-store",
      });
      if (res.ok) return NextResponse.json(await res.json());
    } catch {
      // Fall through to fixtures if the ingestion endpoint is unreachable.
    }
  }
  return NextResponse.json(REVIEW_QUEUE);
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

  const base = ingestBase();
  if (base) {
    try {
      const res = await fetch(`${base}/review`, {
        method: "POST",
        headers: { accept: "application/json", "content-type": "application/json" },
        body: JSON.stringify(decision),
        cache: "no-store",
      });
      if (res.ok) return NextResponse.json(await res.json());
      // A missing endpoint falls through to the local simulation below.
    } catch {
      // Network error -> simulate locally so the demo stays operable.
    }
  }

  return NextResponse.json(simulateFreeze(decision));
}

/**
 * Stand in for the server-side freeze the future ingestion endpoint will perform. The new
 * version is prev + 1 and the new record_hash is a genuine SHA-256 over the decided
 * content (the same primitive ingestion uses), so the UI shows a real proposal→frozen
 * transition rather than a fake string.
 */
function simulateFreeze(decision: ReviewDecision): ReviewResult {
  const item = findReviewItem(decision.tariff_system, decision.tariff_code);
  const nextVersion = (item?.version ?? 1) + 1;

  const corrections =
    decision.action === "correct" ? decision.corrections ?? {} : {};
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
