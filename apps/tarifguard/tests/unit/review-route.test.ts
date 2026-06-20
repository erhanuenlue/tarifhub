import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "@/app/api/review/route";
import type { ReviewDecision, ReviewResult } from "@/lib/api";
import { REVIEW_QUEUE } from "@/lib/review-fixtures";

/**
 * The BFF review route is the console's one write path. With INGEST_BASE_URL unset it
 * serves the offline fixtures; with it set it proxies the queue and the approve/correct
 * decision to the ingestion review endpoint (now implemented) and surfaces its failures.
 * The billing-field guard is enforced here before any proxy call.
 */

const BASE = "https://ingestion.internal";

function postRequest(decision: Partial<ReviewDecision>): NextRequest {
  return new NextRequest("http://localhost/api/review", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(decision),
  });
}

function okResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  delete process.env.INGEST_BASE_URL;
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.INGEST_BASE_URL;
});

describe("review BFF route", () => {
  it("GET serves the fixture queue offline (INGEST_BASE_URL unset, no fetch)", async () => {
    const res = await GET();
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body).toEqual(REVIEW_QUEUE);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("GET proxies to the ingestion review queue when INGEST_BASE_URL is set", async () => {
    process.env.INGEST_BASE_URL = `${BASE}/`;
    const queue = [{ tariff_system: "EAL", tariff_code: "0010.00" }];
    fetchMock.mockResolvedValueOnce(okResponse(queue));

    const res = await GET();
    const body = await res.json();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/review/queue`); // trailing slash stripped
    expect(res.status).toBe(200);
    expect(body).toEqual(queue);
  });

  it("POST forwards an approve decision and returns the freeze result", async () => {
    process.env.INGEST_BASE_URL = BASE;
    const result: ReviewResult = {
      ok: true,
      tariff_system: "EAL",
      tariff_code: "0010.00",
      action: "approve",
      frozen: true,
      version: 2,
      record_hash: "a".repeat(64),
      message: "Approved the proposal verbatim and froze v2.",
    };
    fetchMock.mockResolvedValueOnce(okResponse(result));

    const res = await POST(
      postRequest({ tariff_system: "EAL", tariff_code: "0010.00", record_hash: null, action: "approve" })
    );
    const body = await res.json();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/review`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body).action).toBe("approve");
    expect(res.status).toBe(200);
    expect(body).toEqual(result);
  });

  it("POST rejects a billing-field correction with 400 before proxying", async () => {
    process.env.INGEST_BASE_URL = BASE;
    const res = await POST(
      postRequest({
        tariff_system: "EAL",
        tariff_code: "0010.00",
        record_hash: null,
        action: "correct",
        corrections: { tax_points: "99.99" },
      })
    );
    const body = await res.json();

    expect(res.status).toBe(400);
    // The BFF's own error is the same RFC 7807 envelope the Python services emit.
    expect(res.headers.get("content-type")).toContain("application/problem+json");
    expect(body.detail).toContain("tax_points");
    expect(body).toMatchObject({
      type: expect.any(String),
      title: expect.any(String),
      status: 400,
      instance: "/api/review",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POST surfaces an ingestion backend failure (status + body, never masked as success)", async () => {
    process.env.INGEST_BASE_URL = BASE;
    fetchMock.mockResolvedValueOnce(okResponse({ detail: "record_hash stale" }, 409));

    const res = await POST(
      postRequest({ tariff_system: "EAL", tariff_code: "0010.00", record_hash: "stale", action: "approve" })
    );
    const body = await res.json();

    expect(res.status).toBe(409);
    // A proxy surfaces the upstream problem+json body verbatim under the problem media type,
    // so the console sees ONE envelope end to end (never a re-wrapped or masked failure).
    expect(res.headers.get("content-type")).toContain("application/problem+json");
    expect(body).toEqual({ detail: "record_hash stale" });
  });

  it("POST surfaces a full upstream problem+json document verbatim (one envelope end to end)", async () => {
    process.env.INGEST_BASE_URL = BASE;
    const upstream = {
      type: "https://tarifhub.example/problems/review-conflict",
      title: "Review conflict",
      status: 409,
      detail: "record_hash does not match the current flagged version (stale read)",
      instance: "/review",
    };
    fetchMock.mockResolvedValueOnce(okResponse(upstream, 409));

    const res = await POST(
      postRequest({ tariff_system: "EAL", tariff_code: "0010.00", record_hash: "stale", action: "approve" })
    );
    const body = await res.json();

    expect(res.status).toBe(409);
    expect(res.headers.get("content-type")).toContain("application/problem+json");
    expect(body).toEqual(upstream); // relayed unchanged, not re-wrapped
  });
});
