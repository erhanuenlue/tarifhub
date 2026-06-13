/**
 * Brand primitives that carry the visual law (docs/brand/tokens.css,
 * .claude/rules/demo-frontend.md). All are pure, synchronous, prop-driven components so
 * they render identically in server and client trees and are unit-testable in jsdom.
 *
 * The law, encoded here:
 *   - Frozen / deterministic billing values  -> <CertifiedValue> (.value-certified: navy mono).
 *   - Version + provenance                    -> <VersionChip> / <HashChip> (sky-tint chips).
 *   - AI-generated explanation                -> <AiContent> (labelled .ai-content slate surface).
 * Frozen and AI surfaces are NEVER styled alike and never blended in one element.
 */
import type { ReactNode } from "react";

import { shortHash } from "@/lib/api";

/** A frozen, deterministic billing value. Navy JetBrains Mono, tabular. Renders "—" for null. */
export function CertifiedValue({
  value,
  unit,
  ariaLabel,
}: {
  value: string | null | undefined;
  unit?: string | null;
  ariaLabel?: string;
}) {
  if (value === null || value === undefined || value === "") {
    return (
      <span className="value-certified text-muted" aria-label={ariaLabel}>
        —
      </span>
    );
  }
  return (
    <span className="value-certified" aria-label={ariaLabel}>
      {value}
      {unit ? <span className="ml-1 align-baseline text-xs font-medium text-muted">{unit}</span> : null}
    </span>
  );
}

/** Frozen-version chip. */
export function VersionChip({ version }: { version: number }) {
  return (
    <span className="chip-version" title={`frozen version ${version}`}>
      v{version}
    </span>
  );
}

/** Truncated record_hash chip (mono); full hash on hover. */
export function HashChip({ hash }: { hash: string | null }) {
  return (
    <span
      className="inline-flex items-center rounded-full bg-sky-tint px-2 py-0.5 font-mono text-[11px] text-navy"
      title={hash ?? "unhashed"}
    >
      {shortHash(hash)}
    </span>
  );
}

/** Tariff-system badge. Navy text on a faint navy tint (sky stays a signal, not text). */
export function SystemBadge({ system }: { system: string }) {
  return (
    <span className="inline-flex items-center rounded bg-navy/5 px-2 py-0.5 text-xs font-semibold tracking-wide text-navy">
      {system}
    </span>
  );
}

/** "requires review" pill (warning tone). */
export function ReviewPill() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
      requires review
    </span>
  );
}

/** Validity window, dates in tabular mono (open ends spelled out). */
export function ValidityWindow({ from, to }: { from: string | null; to: string | null }) {
  return (
    <span className="font-mono text-sm tabular-nums text-body">
      {from ?? "—"} <span className="text-muted">→</span> {to ?? "open"}
    </span>
  );
}

/** Source provenance: a link to the source document plus the source version. */
export function Provenance({ url, version }: { url: string | null; version: string | null }) {
  if (!url && !version) return <span className="text-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-2 text-sm">
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="text-blue underline underline-offset-2 hover:text-navy"
        >
          source document
        </a>
      ) : null}
      {version ? <span className="font-mono text-xs text-muted">{version}</span> : null}
    </span>
  );
}

/**
 * The labelled AI surface. The "AI-generated — not a billing value" label is rendered by
 * the .ai-content::before rule (brand-fixed). Never put a frozen value inside this surface.
 */
export function AiContent({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={`ai-content${className ? ` ${className}` : ""}`}>{children}</div>;
}

/** Harmonization-confidence meter. Below the 0.85 review threshold it reads warning. */
export function ConfidenceMeter({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(1, value));
  const pct = Math.round(clamped * 100);
  const low = value < 0.85;
  return (
    <span className="inline-flex items-center gap-2" aria-label={`confidence ${pct}%`}>
      <span className="block h-1.5 w-24 overflow-hidden rounded-full bg-line" aria-hidden>
        <span
          className={`block h-full ${low ? "bg-warning" : "bg-success"}`}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className={`font-mono text-xs tabular-nums ${low ? "text-warning" : "text-success"}`}>
        {pct}%
      </span>
    </span>
  );
}
