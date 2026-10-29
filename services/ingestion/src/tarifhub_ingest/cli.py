"""Minimal ingestion CLI: ``python -m tarifhub_ingest.cli --path <file> --system SL``.

Builds a :class:`SourceSpec` (parser kind from the system: SL -> bag_epl, EAL -> bag_eal),
wires the Database / repository / audit logger from environment settings, runs the
deterministic pipeline, and prints the report. ``--refill`` bypasses AI fill-reuse so a
deliberate re-fill can supersede the prior version; ``--embeddings`` selects the offline
stub (default) or the e5 backend. ``--manifest data/manifests/bag-al.json`` instead imports
the manifest's dated AL editions oldest first, as one transaction, after verifying every
listed document and the stored EAL history; an unsafe batch exits 2 with every problem
listed and no tariff or audit row written. No AI imports beyond what the pipeline already
pulls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import Settings, get_settings
from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.ingestion.manifest import EditionOutcome, ManifestError, import_manifest
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
    parser.add_argument("--path", type=Path, help="Source file to ingest")
    parser.add_argument(
        "--system", choices=sorted(s.value for s in _KIND_BY_SYSTEM),
        help="Tariff system (selects the parser): SL or EAL",
    )
    parser.add_argument(
        "--manifest", type=Path,
        help="Import the dated BAG AL editions this manifest lists (instead of --path)",
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
    if args.manifest is not None:
        if args.path is not None or args.system is not None or args.refill:
            parser.error("--manifest cannot be combined with --path, --system or --refill")
    elif args.path is None or args.system is None:
        parser.error("--path and --system are required unless --manifest is given")

    settings = get_settings()
    if args.embeddings:
        # Override only the embeddings backend for this run; everything else from env.
        settings = type(settings)(**{**settings.__dict__, "embeddings_backend": args.embeddings})

    db = Database.from_url(settings.db_url)
    conn = db.connect()
    db.init_schema(conn)
    try:
        if args.manifest is not None:
            return _import_manifest(args.manifest, conn, db, settings)
        repo = TariffRepository(conn, db)
        audit = AuditLogger(conn, db)
        system = TariffSystem(args.system)
        spec = SourceSpec(
            system=system,
            kind=_KIND_BY_SYSTEM[system],
            path=args.path,
            source_url=_SOURCE_URL_BY_SYSTEM[system],
        )
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


def _import_manifest(path: Path, conn, db: Database, settings: Settings) -> int:
    """Run a manifest import (one transaction); print its report, or its refusal (exit 2)."""

    try:
        result = import_manifest(
            path, conn, db, settings=settings, embedder=get_embedder(settings)
        )
    except ManifestError as exc:  # the import has rolled back
        print(json.dumps({
            "error": "manifest import refused, no tariff or audit row was written",
            "problems": list(exc.problems),
        }, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({
        "manifest": str(path),
        "editions": [_edition_summary(outcome) for outcome in result.editions],
    }, ensure_ascii=False))
    return 0


def _edition_summary(outcome: EditionOutcome) -> dict:
    """One edition's outcome as JSON-ready data (counts only when it was imported)."""

    summary = {
        "effective_date": outcome.effective_date.isoformat(),
        "source_version": outcome.source_version,
        "path": outcome.path,
        "action": outcome.action,
        "already_stored": outcome.already_stored,
    }
    if outcome.report is not None:
        summary.update(
            processed=outcome.report.processed,
            frozen=outcome.report.frozen,
            skipped_existing=outcome.report.skipped_existing,
            flagged_for_review=outcome.report.flagged_for_review,
            parse_failures=outcome.report.parse_failures,
        )
    return summary


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
