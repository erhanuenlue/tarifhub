import { notFound } from "next/navigation";

import { DetailPanel } from "@/components/DetailPanel";
import { getExplain, getTariff, ServingError, type TariffRecord } from "@/lib/api";

/**
 * Frozen-record detail (server component). Fetches the record on the server so
 * SERVING_BASE_URL stays server-side, then best-effort enriches it with the deterministic
 * explain endpoint (version history + cross-system presence). A missing record is a 404.
 */
export default async function DetailPage({
  params,
}: {
  params: Promise<{ system: string; code: string }>;
}) {
  const { system, code } = await params;
  const sys = decodeURIComponent(system);
  const cod = decodeURIComponent(code);

  let record: TariffRecord;
  try {
    record = await getTariff(sys, cod);
  } catch (err) {
    if (err instanceof ServingError && err.status === 404) notFound();
    throw err;
  }

  let versions: TariffRecord[] = [];
  let crosswalkSystems: string[] = [];
  try {
    const explained = await getExplain(record.tariff_code);
    // Version history is this record's own system; cross-walk lists the OTHER systems the
    // same code appears in (explain returns every system for the code).
    versions = explained.records.filter((r) => r.tariff_system === record.tariff_system);
    crosswalkSystems = Array.from(
      new Set(explained.records.map((r) => r.tariff_system))
    ).filter((s) => s !== record.tariff_system);
  } catch {
    // Explain is an optional enrichment; the detail renders fine on the record alone.
  }

  return <DetailPanel record={record} versions={versions} crosswalkSystems={crosswalkSystems} />;
}
