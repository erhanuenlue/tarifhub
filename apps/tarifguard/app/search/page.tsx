"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { TariffCard } from "@/components/TariffCard";
import type { SearchHit, TariffRecord } from "@/lib/api";

type Row = { record: TariffRecord; rank?: number };

const SYSTEMS = ["TARDOC", "EAL", "SL"];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [mode, setMode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (url: string, label: string, asHits: boolean) => {
    setLoading(true);
    setError(null);
    setMode(label);
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "request failed");
      const next: Row[] = asHits
        ? (data as SearchHit[]).map((h) => ({ record: h.record, rank: h.rank }))
        : (data as TariffRecord[]).map((r) => ({ record: r }));
      setRows(next);
    } catch (err) {
      setError((err as Error).message);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Populate with the latest frozen records so the master list is never empty.
  useEffect(() => {
    void load("/api/tariffs?limit=12", "latest frozen records", false);
  }, [load]);

  function runSearch(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!q) {
      void load("/api/tariffs?limit=12", "latest frozen records", false);
      return;
    }
    void load(`/api/search?q=${encodeURIComponent(q)}`, `search · “${q}”`, true);
  }

  function browse(system: string) {
    setQuery("");
    void load(`/api/tariffs?system=${encodeURIComponent(system)}&limit=24`, `system · ${system}`, false);
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-navy">Tariff search</h1>
        <p className="mt-1 text-sm text-body">
          Semantic and code search over frozen records. Results are ranked by the serving API
          and shown verbatim — open a record for its certified value and provenance.
        </p>
      </header>

      <form onSubmit={runSearch} className="flex flex-wrap items-end gap-3">
        <label className="flex-1">
          <span className="block text-xs font-medium text-muted">Query</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Blutzucker, Grundkonsultation, AA.00.0010"
            className="mt-1 w-full rounded-md border border-line bg-card px-3 py-2 text-sm text-navy outline-none focus:border-sky"
            aria-label="search query"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-blue px-4 py-2 text-sm font-medium text-white transition hover:bg-navy disabled:opacity-50"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted">Browse:</span>
        {SYSTEMS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => browse(s)}
            className="rounded-full border border-line px-3 py-1 font-medium text-navy transition hover:border-sky hover:bg-bg"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="flex items-baseline justify-between">
        <p className="text-xs uppercase tracking-wide text-muted">{mode}</p>
        {!loading ? <p className="text-xs text-muted">{rows.length} record(s)</p> : null}
      </div>

      {error ? <p className="blocked rounded-md px-3 py-2 text-sm">{error}</p> : null}

      {!loading && !error && rows.length === 0 ? (
        <p className="rounded-md border border-line bg-card px-3 py-6 text-center text-sm text-muted">
          No records found.
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        {rows.map((row) => (
          <TariffCard key={`${row.record.tariff_system}/${row.record.tariff_code}`} record={row.record} rank={row.rank} />
        ))}
      </div>

      <DisclaimerBanner />
    </div>
  );
}
