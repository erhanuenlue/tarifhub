"use client";

import { type FormEvent, useState } from "react";

import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { TariffCard } from "@/components/TariffCard";
import type { SearchHit } from "@/lib/api";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [system, setSystem] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function runSearch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ q: query });
      if (system) params.set("system", system);
      const res = await fetch(`/api/search?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "search failed");
      setHits(data as SearchHit[]);
    } catch (err) {
      setError((err as Error).message);
      setHits([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Tariff search</h1>
        <p className="mt-1 text-sm text-slate-600">
          Semantic search over frozen records. Results are ranked by the backend and
          shown verbatim.
        </p>
      </header>

      <form onSubmit={runSearch} className="flex flex-wrap items-end gap-3">
        <label className="flex-1">
          <span className="block text-xs text-slate-500">Query</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. blood glucose measurement"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
            required
          />
        </label>
        <label>
          <span className="block text-xs text-slate-500">System (optional)</span>
          <input
            value={system}
            onChange={(e) => setSystem(e.target.value)}
            placeholder="TARDOC"
            className="mt-1 w-32 rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        {hits.map((hit) => (
          <TariffCard key={hit.record.recordHash} record={hit.record} rank={hit.rank} />
        ))}
      </div>

      <DisclaimerBanner />
    </div>
  );
}
