import Link from "next/link";

import { CertifiedValue, HashChip, ReviewPill, SystemBadge, VersionChip } from "@/components/brand";
import { primaryValue, type TariffRecord } from "@/lib/api";

/**
 * One frozen record in the master list. Values (tax points, price) are shown exactly as
 * returned by serving — this component formats layout, never numbers. The whole card is
 * the master→detail link.
 */
export function TariffCard({ record, rank }: { record: TariffRecord; rank?: number }) {
  const { value, unit } = primaryValue(record);
  const href = `/tariffs/${encodeURIComponent(record.tariff_system)}/${encodeURIComponent(
    record.tariff_code
  )}`;
  return (
    <Link
      href={href}
      className="block rounded-lg border border-line bg-card p-4 transition hover:border-sky hover:shadow-sm"
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          {rank ? <span className="font-mono text-xs text-muted">#{rank}</span> : null}
          <SystemBadge system={record.tariff_system} />
          <span className="font-mono text-sm font-semibold text-navy">{record.tariff_code}</span>
        </div>
        {record.requires_review ? <ReviewPill /> : null}
      </div>

      <p className="mt-2 line-clamp-2 text-sm text-body">{record.designation.de || "—"}</p>

      <div className="mt-3 flex items-center justify-between gap-2">
        <CertifiedValue value={value} unit={unit} ariaLabel="current value" />
        <span className="flex items-center gap-2">
          <VersionChip version={record.version} />
          <HashChip hash={record.record_hash} />
        </span>
      </div>
    </Link>
  );
}
