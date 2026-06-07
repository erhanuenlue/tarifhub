"use client";

import { type FormEvent, type ReactNode, useState } from "react";

import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import type { CodingFlag, CodingPosition } from "@/lib/api";

/** Parse pasted lines like "TARDOC 00.0010", "TARDOC/00.0010" or "00.0010". */
function parsePositions(raw: string): CodingPosition[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(/[\s/]+/);
      if (parts.length >= 2) {
        return { system: parts[0], code: parts[1] };
      }
      return { system: "TARDOC", code: parts[0] };
    });
}

export default function CodingCheckPage() {
  const [raw, setRaw] = useState("");
  const [flags, setFlags] = useState<CodingFlag[]>([]);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function runCheck(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const positions = parsePositions(raw);
      const res = await fetch("/api/coding-check", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ positions }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "coding check failed");
      setFlags(data.flags as CodingFlag[]);
      setSource(data.source as string);
    } catch (err) {
      setError((err as Error).message);
      setFlags([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Coding check</h1>
        <p className="mt-1 text-sm text-slate-600">
          Paste coded encounter positions (one per line). The deterministic backend
          decides combinability and validity; TarifGuard only displays the flags.
        </p>
      </header>

      <form onSubmit={runCheck} className="space-y-3">
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          rows={6}
          placeholder={"TARDOC 00.0010\nTARDOC 00.0020\nTARDOC AA.00.0050"}
          className="w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm"
          required
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {loading ? "Checking…" : "Check coding"}
        </button>
      </form>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {source ? (
        <p className="text-xs text-slate-400">
          verdicts from: <span className="font-mono">{source}</span>
        </p>
      ) : null}

      <ul className="space-y-2">
        {flags.map((flag, i) => (
          <li
            key={`${flag.position.system}-${flag.position.code}-${i}`}
            className="rounded border border-slate-200 bg-white p-3 text-sm"
          >
            <div className="flex items-center justify-between">
              <span className="font-mono">
                {flag.position.system} {flag.position.code}
              </span>
              <span className="flex gap-2">
                {!flag.found ? <Badge tone="red">not found</Badge> : null}
                {flag.requiresReview ? <Badge tone="amber">requires review</Badge> : null}
                {flag.outsideValidity ? <Badge tone="amber">outside validity</Badge> : null}
                {flag.found && !flag.requiresReview && !flag.outsideValidity ? (
                  <Badge tone="green">ok</Badge>
                ) : null}
              </span>
            </div>
            {flag.messages.length > 0 ? (
              <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">
                {flag.messages.map((m, j) => (
                  <li key={j}>{m}</li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>

      <DisclaimerBanner />
    </div>
  );
}

function Badge({ tone, children }: { tone: "red" | "amber" | "green"; children: ReactNode }) {
  const tones = {
    red: "bg-red-100 text-red-800",
    amber: "bg-amber-100 text-amber-800",
    green: "bg-green-100 text-green-800",
  };
  return <span className={`rounded px-2 py-0.5 text-xs ${tones[tone]}`}>{children}</span>;
}
