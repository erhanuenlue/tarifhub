"use client";

import { useEffect, useMemo, useState } from "react";

import {
  CertifiedValue,
  ConfidenceMeter,
  HashChip,
  ReviewPill,
  SystemBadge,
  VersionChip,
} from "@/components/brand";
import { shortHash, type ReviewDecision, type ReviewItem, type ReviewResult } from "@/lib/api";

const keyOf = (i: ReviewItem) => `${i.tariff_system}/${i.tariff_code}`;

export function ReviewForm() {
  const [queue, setQueue] = useState<ReviewItem[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Field-level correction overrides for the active item, keyed by field name.
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ReviewResult | null>(null);

  const active = useMemo(
    () => queue.find((i) => keyOf(i) === activeKey) ?? null,
    [queue, activeKey]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/review");
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? "failed to load review queue");
        if (cancelled) return;
        setQueue(data as ReviewItem[]);
        setActiveKey((data as ReviewItem[])[0] ? keyOf((data as ReviewItem[])[0]) : null);
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function selectItem(k: string) {
    setActiveKey(k);
    setCorrections({});
    setResult(null);
  }

  async function submit(action: "approve" | "correct") {
    if (!active) return;
    setSubmitting(true);
    setError(null);
    const editable = active.fields.filter((f) => !f.billing);
    const decision: ReviewDecision = {
      tariff_system: active.tariff_system,
      tariff_code: active.tariff_code,
      record_hash: active.record_hash,
      action,
      reviewer: "demo-reviewer",
      corrections:
        action === "correct"
          ? Object.fromEntries(
              editable.map((f) => [f.field, corrections[f.field] ?? f.proposal ?? ""])
            )
          : undefined,
    };
    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(decision),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "submit failed");
      setResult(data as ReviewResult);
      // Remove the now-frozen item from the queue.
      setQueue((q) => q.filter((i) => keyOf(i) !== keyOf(active)));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <p className="text-sm text-muted">Loading review queue…</p>;
  if (error && queue.length === 0)
    return <p className="blocked rounded-md px-3 py-2 text-sm">{error}</p>;

  return (
    <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
      {/* Queue */}
      <aside className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          Flagged for review ({queue.length})
        </p>
        {queue.length === 0 ? (
          <p className="rounded-md border border-line bg-card px-3 py-4 text-sm text-muted">
            Queue clear — every flagged record has been decided.
          </p>
        ) : (
          <ul className="space-y-2">
            {queue.map((i) => {
              const k = keyOf(i);
              const selected = k === activeKey;
              return (
                <li key={k}>
                  <button
                    type="button"
                    onClick={() => selectItem(k)}
                    className={`w-full rounded-lg border p-3 text-left transition ${
                      selected ? "border-sky bg-bg" : "border-line bg-card hover:border-sky"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <SystemBadge system={i.tariff_system} />
                      <span className="font-mono text-sm font-semibold text-navy">{i.tariff_code}</span>
                    </span>
                    <span className="mt-1 block line-clamp-1 text-xs text-body">{i.designation_de}</span>
                    <span className="mt-2 block">
                      <ConfidenceMeter value={i.confidence} />
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </aside>

      {/* Active review */}
      <section>
        {result ? (
          <FrozenResult result={result} onNext={() => setResult(null)} hasMore={queue.length > 0} />
        ) : active ? (
          <ReviewDetail
            item={active}
            corrections={corrections}
            onCorrect={(field, value) => setCorrections((c) => ({ ...c, [field]: value }))}
            onApprove={() => submit("approve")}
            onSubmitCorrections={() => submit("correct")}
            submitting={submitting}
            error={error}
          />
        ) : (
          <p className="rounded-md border border-line bg-card px-4 py-8 text-center text-sm text-muted">
            Nothing selected.
          </p>
        )}
      </section>
    </div>
  );
}

function ReviewDetail({
  item,
  corrections,
  onCorrect,
  onApprove,
  onSubmitCorrections,
  submitting,
  error,
}: {
  item: ReviewItem;
  corrections: Record<string, string>;
  onCorrect: (field: string, value: string) => void;
  onApprove: () => void;
  onSubmitCorrections: () => void;
  submitting: boolean;
  error: string | null;
}) {
  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <SystemBadge system={item.tariff_system} />
          <span className="font-mono text-lg font-semibold text-navy">{item.tariff_code}</span>
          <ReviewPill />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-body">
          <ConfidenceMeter value={item.confidence} />
          <span className="text-xs text-muted">{item.flagged_reason}</span>
        </div>
      </header>

      <p className="text-xs text-muted">
        Left is the deterministic raw extract; right is the{" "}
        <span className="font-semibold uppercase tracking-wide">ai_map proposal — AI-generated, not a billing value</span>.
        Billing values are never AI-filled and stay certified. Correct any proposal, then approve to freeze.
      </p>

      <div className="overflow-hidden rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-bg text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-3 py-2 font-medium">Field</th>
              <th className="px-3 py-2 font-medium">Raw extract</th>
              <th className="px-3 py-2 font-medium">ai_map proposal / correction</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {item.fields.map((f) => (
              <tr key={f.field} className="align-top">
                <td className="px-3 py-2.5">
                  <span className="font-mono text-xs text-navy">{f.label}</span>
                  {f.billing ? (
                    <span className="mt-1 block text-[10px] uppercase tracking-wide text-success">
                      certified · not AI
                    </span>
                  ) : f.aiFilled ? (
                    <span className="mt-1 block text-[10px] uppercase tracking-wide text-muted">
                      AI-filled
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2.5 text-body">
                  {f.billing ? (
                    <CertifiedValue value={f.raw} />
                  ) : (
                    <span className={f.raw ? "text-body" : "text-muted"}>{f.raw ?? "— (empty in source)"}</span>
                  )}
                </td>
                <td className="bg-bg/60 px-3 py-2.5">
                  {f.billing ? (
                    <CertifiedValue value={f.proposal} />
                  ) : (
                    <input
                      value={corrections[f.field] ?? f.proposal ?? ""}
                      onChange={(e) => onCorrect(f.field, e.target.value)}
                      aria-label={`${f.label} proposal`}
                      className="w-full rounded border border-line bg-card px-2 py-1 text-sm text-body outline-none focus:border-sky"
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error ? <p className="blocked rounded-md px-3 py-2 text-sm">{error}</p> : null}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onApprove}
          disabled={submitting}
          className="rounded-md bg-success px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? "Freezing…" : "Approve proposal & freeze"}
        </button>
        <button
          type="button"
          onClick={onSubmitCorrections}
          disabled={submitting}
          className="rounded-md border border-line bg-card px-4 py-2 text-sm font-medium text-navy transition hover:border-sky disabled:opacity-50"
        >
          Freeze with corrections
        </button>
        <span className="text-xs text-muted">
          {item.ai_model ? (
            <>
              proposal by <span className="font-mono">{item.ai_model}</span>
            </>
          ) : null}
        </span>
      </div>
    </div>
  );
}

/** The proposal→frozen transition, made visible: a sealed, certified record. */
function FrozenResult({
  result,
  onNext,
  hasMore,
}: {
  result: ReviewResult;
  onNext: () => void;
  hasMore: boolean;
}) {
  return (
    <div className="space-y-4 rounded-lg border border-success/30 bg-success/5 p-6">
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-success text-sm text-white" aria-hidden>
          ✓
        </span>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-success">Frozen</h2>
      </div>

      <p className="text-sm text-body">{result.message}</p>

      <div className="flex flex-wrap items-center gap-3 rounded-md border border-line bg-card px-4 py-3">
        <SystemBadge system={result.tariff_system} />
        <span className="font-mono text-sm font-semibold text-navy">{result.tariff_code}</span>
        <span className="text-muted">proposal</span>
        <span aria-hidden className="text-success">→</span>
        <span className="font-medium text-success">frozen</span>
        <VersionChip version={result.version} />
        <HashChip hash={result.record_hash} />
      </div>

      <p className="text-xs text-muted">
        The record is now immutable: SHA-256 <span className="font-mono">{shortHash(result.record_hash, 16)}</span> over its
        canonical content, served verbatim by the API. No value was computed by the console.
      </p>

      <button
        type="button"
        onClick={onNext}
        className="rounded-md bg-blue px-4 py-2 text-sm font-medium text-white transition hover:bg-navy"
      >
        {hasMore ? "Review next" : "Done"}
      </button>
    </div>
  );
}
