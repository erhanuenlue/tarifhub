"""Minimal ingestion CLI: ``python -m tarifhub_ingest.cli --path <file> --system SL``.

Builds a :class:`SourceSpec` (parser kind from the system: SL -> bag_epl, EAL -> bag_eal),
wires the Database / repository / audit logger from environment settings, runs the
deterministic pipeline, and prints the report. ``--refill`` bypasses AI fill-reuse so a
deliberate re-fill can supersede the prior version; ``--embeddings`` selects the offline
stub (default) or the e5 backend. No AI imports beyond what the pipeline already pulls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import get_settings
from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.ingestion.pipeline import run_pipeline
from tarifhub_ingest.ingestion.source_loader import SourceSpec
from tarifhub_ingest.models.tariff_model import TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository

# Parser kind per tariff system (mirrors the discover_samples wiring for real BAG feeds).
_KIND_BY_SYSTEM = {TariffSystem.SL: "bag_epl", TariffSystem.EAL: "bag_eal"}
_SOURCE_URL_BY_SYSTEM = {
    TariffSystem.SL: "https://epl.bag.admin.ch",
    TariffSystem.EAL: "https://www.bag.admin.ch/de/analysenliste-al",
}


def main(argv: list[str] | None = None) -> int:
    """Run the ingestion pipeline over one source file; return a process exit code."""

    parser = argparse.ArgumentParser(prog="tarifhub-ingest", description=__doc__)
    parser.add_argument("--path", required=True, type=Path, help="Source file to ingest")
    parser.add_argument(
        "--system", required=True, choices=sorted(s.value for s in _KIND_BY_SYSTEM),
        help="Tariff system (selects the parser): SL or EAL",
    )
    parser.add_argument(
        "--refill", action="store_true",
        help="Bypass AI fill-reuse and re-run ai_map (deliberate re-fill)",
    )
    parser.add_argument(
        "--embeddings", choices=("stub", "e5"), default=None,
        help="Embedding backend; default is the env/offline stub",
    )
    args = parser.parse_args(argv)

    system = TariffSystem(args.system)
    spec = SourceSpec(
        system=system,
        kind=_KIND_BY_SYSTEM[system],
        path=args.path,
        source_url=_SOURCE_URL_BY_SYSTEM[system],
    )

    settings = get_settings()
    if args.embeddings:
        # Override only the embeddings backend for this run; everything else from env.
        settings = type(settings)(**{**settings.__dict__, "embeddings_backend": args.embeddings})

    db = Database.from_url(settings.db_url)
    conn = db.connect()
    db.init_schema(conn)
    try:
        repo = TariffRepository(conn, db)
        audit = AuditLogger(conn, db)
        report = run_pipeline(
            [spec], repo, audit,
            settings=settings, embedder=get_embedder(settings), refill=args.refill,
        )
    finally:
        conn.close()

    print(json.dumps({
        "system": system.value,
        "path": str(args.path),
        "refill": args.refill,
        "processed": report.processed,
        "frozen": report.frozen,
        "skipped_existing": report.skipped_existing,
        "flagged_for_review": report.flagged_for_review,
        "parse_failures": report.parse_failures,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
