/**
 * Minimal mock of the deterministic serving API (L1 TarifCore) for the offline Playwright
 * smoke and for screenshot capture. Dependency-free Node http server. It returns the canonical
 * wire shape (snake_case TariffRecord, nested designation, SearchHit, ExplainResponse) so the
 * console runs end-to-end with no live backend and no network. Port: MOCK_PORT or 8799.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_PORT) || 8799;

const r = (over) => ({
  tariff_code: "",
  tariff_system: "TARDOC",
  designation: { de: "", fr: null, it: null },
  category: null,
  tax_points: null,
  price_chf: null,
  unit: null,
  valid_from: "2024-01-01",
  valid_to: null,
  source_url: null,
  source_version: "2024.1",
  harmonization_confidence: 0.95,
  requires_review: false,
  metadata: {},
  record_hash: null,
  version: 1,
  created_at: "2024-02-15T10:30:00Z",
  ...over,
});

// All versions across keys (explain returns the full version list; list/get return the latest).
const ALL = [
  r({
    tariff_code: "AA.00.0010",
    tariff_system: "TARDOC",
    designation: { de: "Grundkonsultation", fr: null, it: null },
    category: "Grundleistungen",
    tax_points: "9.57",
    version: 1,
    source_url: "https://www.tardoc.example/AA.00.0010",
    record_hash: "1".repeat(64),
  }),
  r({
    tariff_code: "AA.00.0010",
    tariff_system: "TARDOC",
    designation: { de: "Grundkonsultation (rev)", fr: "Consultation de base (rév)", it: null },
    category: "Grundleistungen",
    tax_points: "10.10",
    version: 2,
    source_url: "https://www.tardoc.example/AA.00.0010",
    record_hash: "2".repeat(64),
  }),
  r({
    tariff_code: "BB.00.0020",
    tariff_system: "TARDOC",
    designation: { de: "Zuschlag Komplexität", fr: null, it: null },
    category: "Zuschläge",
    tax_points: "4.25",
    record_hash: "3".repeat(64),
  }),
  r({
    tariff_code: "1234.00",
    tariff_system: "EAL",
    designation: { de: "Blutzucker (Glukose)", fr: null, it: null },
    category: "Klinische Chemie",
    tax_points: "2.50",
    unit: "Bestimmung",
    source_url: "https://www.bag.admin.ch/eal/1234.00",
    record_hash: "4".repeat(64),
  }),
  r({
    tariff_code: "7680565740013",
    tariff_system: "SL",
    designation: {
      de: "Dafalgan, Tabletten 500 mg",
      fr: "Dafalgan, comprimés 500 mg",
      it: "Dafalgan, compresse 500 mg",
    },
    category: "Analgetika",
    price_chf: "4.85",
    source_url: "https://www.spezialitaetenliste.ch/7680565740013",
    record_hash: "5".repeat(64),
    metadata: {
      mapper_version: "tariff-mapper/0.1.0",
      ai_assisted: true,
      ai_model: "claude-opus-4-8",
      ai_status: "ok",
      ai_fields: ["designation_fr", "designation_it"],
    },
  }),
];

function latest() {
  const byKey = new Map();
  for (const rec of ALL) {
    const k = `${rec.tariff_system}/${rec.tariff_code}`;
    const cur = byKey.get(k);
    if (!cur || rec.version > cur.version) byKey.set(k, rec);
  }
  return [...byKey.values()].sort((a, b) =>
    `${a.tariff_system}${a.tariff_code}`.localeCompare(`${b.tariff_system}${b.tariff_code}`)
  );
}

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const p = url.pathname;

  if (p === "/health") return send(res, 200, { status: "ok" });

  if (p === "/api/v1/tariffs") {
    const system = url.searchParams.get("system");
    let rows = latest();
    if (system) rows = rows.filter((x) => x.tariff_system === system);
    const limit = Number(url.searchParams.get("limit")) || 25;
    return send(res, 200, rows.slice(0, limit));
  }

  if (p === "/api/v1/search") {
    const q = (url.searchParams.get("q") || "").toLowerCase();
    const rows = latest().filter(
      (x) => !q || x.tariff_code.toLowerCase().includes(q) || x.designation.de.toLowerCase().includes(q)
    );
    const hits = (rows.length ? rows : latest()).map((rec, i) => ({ rank: i + 1, record: rec }));
    return send(res, 200, hits);
  }

  if (p === "/api/v1/explain") {
    const code = url.searchParams.get("code");
    const recs = ALL.filter((x) => x.tariff_code === code).sort(
      (a, b) => a.version - b.version
    );
    if (!recs.length) return send(res, 404, { detail: `no frozen record for code=${code}` });
    const systems = [...new Set(recs.map((x) => x.tariff_system))].join(", ");
    const current = recs[recs.length - 1];
    return send(res, 200, {
      code,
      records: recs,
      explanation:
        `[deterministic] Tariff code ${code} in system ${systems} resolves to ${recs.length} ` +
        `frozen version(s). The current version is v${current.version}: "${current.designation.de}". ` +
        `This record is served verbatim from a frozen, hashed entry; no value was computed or altered.`,
    });
  }

  const m = p.match(/^\/api\/v1\/tariffs\/([^/]+)\/([^/]+)$/);
  if (m) {
    const system = decodeURIComponent(m[1]);
    const code = decodeURIComponent(m[2]);
    const rows = ALL.filter((x) => x.tariff_system === system && x.tariff_code === code);
    if (!rows.length) return send(res, 404, { detail: `no frozen record for ${system}/${code}` });
    const rec = rows.sort((a, b) => b.version - a.version)[0];
    return send(res, 200, rec);
  }

  return send(res, 404, { detail: "not found" });
});

server.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`mock-serving listening on http://localhost:${PORT}`);
});
