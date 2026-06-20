"use client";

import Link from "next/link";
import { type FormEvent, type ReactNode, useState } from "react";

import { CertifiedValue, SystemBadge } from "@/components/brand";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { primaryValue, type CodingFlag, type CodingPosition } from "@/lib/api";

/** Parse pasted lines like "TARDOC 00.0010", "TARDOC/00.0010" or "00.0010". */
function parsePositions(raw: string): CodingPosition[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(/[\s/]+/);
      return parts.length >= 2 ? { system: parts[0], code: parts[1] } : { system: "TARDOC", code: parts[0] };
    });
}

export default function CodingCheckPage() {
  const [raw, setRaw] = useState("");
  const [flags, setFlags] = useState<CodingFlag[]>([]);
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
      if (!res.ok) throw new Error(data.detail ?? data.error ?? "coding check failed");
      setFlags(data.flags as CodingFlag[]);
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
        <h1 className="text-xl font-semibold text-navy">Coding check</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-body">
          Paste coded positions (one per line). Each is looked up against frozen records —
          existence, review flag and validity window — with the certified value shown
          verbatim. The console computes no combinability verdict.
        </p>
      </header>

      <form onSubmit={runCheck} className="space-y-3">
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          rows={5}
          required
          aria-label="coded positions"
          placeholder={"TARDOC AA.00.0010\nEAL 1234.00\nTARDOC BB.00.0020"}
          className="w-full rounded-md border border-line bg-card px-3 py-2 font-mono text-sm text-navy outline-none focus:border-sky"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-blue px-4 py-2 text-sm font-medium text-white transition hover:bg-navy disabled:opacity-50"
        >
          {loading ? "Checking…" : "Check coding"}
        </button>
      </form>

      {error ? <p className="blocked rounded-md px-3 py-2 text-sm">{error}</p> : null}

      <ul className="space-y-2">
        {flags.map((flag, i) => {
          const ok = flag.found && !flag.requires_review && !flag.outside_validity;
          const pv = flag.record ? primaryValue(flag.record) : { value: null, unit: null };
          return (
            <li
              key={`${flag.position.system}-${flag.position.code}-${i}`}
              className="rounded-lg border border-line bg-card p-3 text-sm"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <SystemBadge system={flag.position.system} />
                  <span className="font-mono font-semibold text-navy">{flag.position.code}</span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  {flag.found ? <CertifiedValue value={pv.value} unit={pv.unit} /> : null}
                  {!flag.found ? <Badge tone="error">not found</Badge> : null}
                  {flag.requires_review ? <Badge tone="warning">requires review</Badge> : null}
                  {flag.outside_validity ? <Badge tone="warning">outside validity</Badge> : null}
                  {ok ? <Badge tone="success">ok</Badge> : null}
                </span>
              </div>
              {flag.messages.length > 0 ? (
                <ul className="mt-2 list-disc pl-5 text-xs text-muted">
                  {flag.messages.map((m, j) => (
                    <li key={j}>{m}</li>
                  ))}
                </ul>
              ) : null}
              {flag.found ? (
                <Link
                  href={`/tariffs/${encodeURIComponent(flag.position.system)}/${encodeURIComponent(flag.position.code)}`}
                  className="mt-2 inline-block text-xs text-blue underline underline-offset-2 hover:text-navy"
                >
                  open detail →
                </Link>
              ) : null}
            </li>
          );
        })}
      </ul>

      <DisclaimerBanner />
    </div>
  );
}

function Badge({ tone, children }: { tone: "error" | "warning" | "success"; children: ReactNode }) {
  const tones = {
    error: "bg-error/10 text-error",
    warning: "bg-warning/10 text-warning",
    success: "bg-success/10 text-success",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}
