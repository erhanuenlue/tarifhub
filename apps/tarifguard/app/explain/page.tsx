"use client";

import { type FormEvent, useState } from "react";

import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { TariffCard } from "@/components/TariffCard";
import type { ExplainResult, TariffRecord } from "@/lib/api";

interface ExplainResponse extends ExplainResult {
  redactions: { rule: string; count: number }[];
  sentPayload: { code?: string; question?: string; context?: string };
  error?: string;
}

export default function ExplainPage() {
  const [code, setCode] = useState("");
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState("");
  const [result, setResult] = useState<ExplainResponse | null>(null);
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
        body: JSON.stringify({ code, question, context }),
      });
      const data = (await res.json()) as ExplainResponse;
      // 501 (endpoint not wired) still carries redactions + payload — show them.
      setResult(data);
      if (!res.ok && res.status !== 501) throw new Error(data.error ?? "explain failed");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Explain</h1>
        <p className="mt-1 text-sm text-slate-600">
          Plain-language explanation and TARMED↔TARDOC cross-walk. Input is
          de-identified before anything leaves the server.
        </p>
      </header>

      <form onSubmit={runExplain} className="space-y-3">
        <label className="block">
          <span className="block text-xs text-slate-500">Position code</span>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="00.0010"
            className="mt-1 w-48 rounded border border-slate-300 px-3 py-2 font-mono text-sm"
            required
          />
        </label>
        <label className="block">
          <span className="block text-xs text-slate-500">Question</span>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What is the TARDOC equivalent and when does it apply?"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="block text-xs text-slate-500">
            Encounter context (optional — identifiers are stripped automatically)
          </span>
          <textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            rows={4}
            placeholder="Consultation incl. diagnosis codes and encounter structure…"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {loading ? "Explaining…" : "Explain"}
        </button>
      </form>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {result ? (
        <div className="space-y-4">
          {result.error ? (
            <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {result.error}
            </p>
          ) : null}

          {result.explanation ? (
            <section className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="text-sm font-semibold text-slate-900">Explanation</h2>
              <p className="mt-2 whitespace-pre-line text-sm text-slate-700">
                {result.explanation}
              </p>
            </section>
          ) : null}

          {result.records?.length ? (
            <section className="grid gap-3 sm:grid-cols-2">
              {result.records.map((record: TariffRecord) => (
                <TariffCard key={record.recordHash} record={record} />
              ))}
            </section>
          ) : null}

          <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <h2 className="text-sm font-semibold text-slate-900">
              De-identification audit
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Exactly what was sent onward (built by lib/deident.ts):
            </p>
            <pre className="mt-2 overflow-x-auto rounded bg-white p-3 text-xs text-slate-700">
              {JSON.stringify(result.sentPayload, null, 2)}
            </pre>
            {result.redactions?.length ? (
              <p className="mt-2 text-xs text-slate-500">
                Redacted:{" "}
                {result.redactions.map((r) => `${r.rule} ×${r.count}`).join(", ")}
              </p>
            ) : (
              <p className="mt-2 text-xs text-slate-500">No direct identifiers detected.</p>
            )}
          </section>
        </div>
      ) : null}

      <DisclaimerBanner />
    </div>
  );
}
