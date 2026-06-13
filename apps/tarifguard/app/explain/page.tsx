"use client";

import { type FormEvent, useState } from "react";

import { AiContent } from "@/components/brand";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { TariffCard } from "@/components/TariffCard";
import type { TariffRecord } from "@/lib/api";

interface ExplainData {
  code?: string;
  records?: TariffRecord[];
  explanation?: string;
  deident?: { scrubbed: string | null; redactions: { rule: string; count: number }[] };
  error?: string;
}

export default function ExplainPage() {
  const [code, setCode] = useState("");
  const [context, setContext] = useState("");
  const [data, setData] = useState<ExplainData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function runExplain(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/explain", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ code: code.trim(), context: context.trim() || undefined }),
      });
      const body = (await res.json()) as ExplainData;
      setData(body);
      if (!res.ok) throw new Error(body.error ?? "explain failed");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-navy">Explain</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-body">
          A record-grounded explanation for a tariff code. The backend explain seam takes a
          code only — the explanation is assembled from frozen records, never invented. Any
          optional clinical context is de-identified server-side and shown as an audit; it is
          never sent to the model.
        </p>
      </header>

      <form onSubmit={runExplain} className="space-y-3">
        <label className="block">
          <span className="block text-xs font-medium text-muted">Tariff code</span>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="AA.00.0010"
            required
            aria-label="tariff code"
            className="mt-1 w-56 rounded-md border border-line bg-card px-3 py-2 font-mono text-sm text-navy outline-none focus:border-sky"
          />
        </label>
        <label className="block">
          <span className="block text-xs font-medium text-muted">
            Clinical context (optional — de-identification demo; never sent to the model)
          </span>
          <textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            rows={3}
            placeholder="Patient: Muster, geb. 12.03.1980 · Konsultation 00.0010 · Diagnose M54.5"
            className="mt-1 w-full rounded-md border border-line bg-card px-3 py-2 text-sm text-body outline-none focus:border-sky"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-blue px-4 py-2 text-sm font-medium text-white transition hover:bg-navy disabled:opacity-50"
        >
          {loading ? "Explaining…" : "Explain"}
        </button>
      </form>

      {error ? <p className="blocked rounded-md px-3 py-2 text-sm">{error}</p> : null}

      {data?.explanation ? (
        <AiContent>
          <p className="whitespace-pre-line text-sm leading-relaxed">{data.explanation}</p>
        </AiContent>
      ) : null}

      {data?.records && data.records.length > 0 ? (
        <section className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">
            Grounded in {data.records.length} frozen record(s)
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {data.records.map((record) => (
              <TariffCard key={`${record.tariff_system}/${record.tariff_code}/${record.version}`} record={record} />
            ))}
          </div>
        </section>
      ) : null}

      {data?.deident && (data.deident.scrubbed || data.deident.redactions.length > 0) ? (
        <section className="rounded-lg border border-line bg-card p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">
            De-identification seam (ADR-012)
          </h2>
          <p className="mt-1 text-xs text-muted">
            What lib/deident.ts produced from the optional context. This never leaves the server.
          </p>
          {data.deident.scrubbed ? (
            <pre className="mt-2 overflow-x-auto rounded bg-bg p-3 text-xs text-body">
              {data.deident.scrubbed}
            </pre>
          ) : null}
          <p className="mt-2 text-xs text-muted">
            {data.deident.redactions.length > 0
              ? `Redacted: ${data.deident.redactions.map((r) => `${r.rule} ×${r.count}`).join(", ")}`
              : "No direct identifiers detected."}
          </p>
        </section>
      ) : null}

      <DisclaimerBanner />
    </div>
  );
}
