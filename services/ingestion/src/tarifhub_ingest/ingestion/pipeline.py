"""The deterministic pre-freeze pipeline.

For each source, in a fixed order:
    load -> parse -> map -> validate -> score -> flag -> freeze -> store -> audit

Everything is a pure function of the inputs (no randomness, no wall-clock branching),
so the same sources always produce the same frozen records and hashes. AI may assist
only at the ``map`` step (via :func:`ai_map`) and never touches a billing value.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import Settings, get_settings
from tarifhub_ingest.confidence.scorer import score
from tarifhub_ingest.embeddings.embedder import Embedder
from tarifhub_ingest.ingestion.fill_reuse import reuse_or_none
from tarifhub_ingest.ingestion.source_loader import SourceSpec
from tarifhub_ingest.mappers.tariff_mapper import ai_map, map_raw
from tarifhub_ingest.models.tariff_model import TariffRecord
from tarifhub_ingest.adapters import bag_eal, bag_epl
from tarifhub_ingest.parsers import xlsx_parser
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.validators.tariff_validator import validate
from tarifhub_ingest.versioning.freeze_record import freeze

_PARSERS = {
    "xlsx": (xlsx_parser.parse, xlsx_parser.PARSER_VERSION),
    "bag_eal": (bag_eal.parse, bag_eal.ADAPTER_VERSION),
    "bag_epl": (bag_epl.parse, bag_epl.ADAPTER_VERSION),
}


@dataclass
class PipelineReport:
    """Summary of a single pipeline run."""

    processed: int = 0
    frozen: int = 0
    skipped_existing: int = 0
    flagged_for_review: int = 0
    parse_failures: int = 0  # rows an adapter could not key -> never mapped/frozen
    records: list[TariffRecord] = field(default_factory=list)


def run_pipeline(  # noqa: PLR0913 — sources + ports + keyword-only pipeline knobs
    specs: list[SourceSpec],
    repo: TariffRepository,
    audit: AuditLogger,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    refill: bool = False,
) -> PipelineReport:
    """Run the full pipeline for the given sources and return a report.

    ``refill=False`` (default) carries an unchanged row's prior AI fills forward with no
    model call (re-ingest idempotency, even key-less). ``refill=True`` bypasses reuse and
    re-runs ``ai_map`` so a deliberate re-fill can supersede the prior version.
    """

    settings = settings or get_settings()
    report = PipelineReport()

    for spec in sorted(specs, key=lambda s: (s.system.value, str(s.path))):
        _, parser_version = _PARSERS[spec.kind]
        for raw in source_rows(spec):
            # Fail-closed marker: the adapter could not key this row (e.g. a
            # reimbursed package with no GTIN). Count it and never map/freeze it —
            # a parsing failure must never produce a frozen record.
            if raw.get("_parse_failure"):
                report.parse_failures += 1
                continue

            report.processed += 1

            # Fill-reuse seam (repo lives here; ai_map stays repo-free). When source
            # content is unchanged from the latest frozen version we adopt that version's
            # content verbatim — AI fills included — with NO model call, so freeze
            # reproduces the identical hash and the row dedupes. This short-circuits
            # BEFORE ai_map / the key check, which also fixes the key-less inverse bug.
            reuse = None
            if not refill:
                candidate = map_raw(
                    raw, system=spec.system, source_url=spec.source_url
                )
                reuse = reuse_or_none(candidate, repo, spec.system)
            if reuse is not None:
                record = reuse.record
            else:
                record = ai_map(
                    raw,
                    system=spec.system,
                    source_url=spec.source_url,
                    settings=settings,
                )

            result = validate(record)
            confidence = score(record)
            requires_review = (confidence < settings.review_threshold) or (not result.ok)
            record = record.model_copy(
                update={
                    "harmonization_confidence": confidence,
                    "requires_review": requires_review,
                }
            )
            if requires_review:
                report.flagged_for_review += 1

            frozen = freeze(record)
            embedding = None
            if embedder is not None:
                text = f"{frozen.tariff_system.value} {frozen.tariff_code} {frozen.designation.de}"
                embedding = embedder.embed(text)

            stored = repo.add(frozen, embedding=embedding)
            if stored:
                report.frozen += 1
                report.records.append(frozen)
            else:
                report.skipped_existing += 1

            # Reuse provenance goes into the audit detail ONLY — never into the record
            # metadata, which would change the hashed bytes and re-version the record
            # (the deliberate byte-stability trade-off behind fill-reuse).
            detail = {"errors": result.errors, "warnings": result.warnings}
            if reuse is not None:
                detail["ai_fills_reused"] = True
                detail["reused_from_version"] = reuse.reused_from_version

            audit.log(
                event_type="freeze" if stored else "freeze_skipped_idempotent",
                record=frozen,
                source_file=str(spec.path),
                parser_version=parser_version,
                confidence=confidence,
                validation_ok=result.ok,
                detail=detail,
            )

    return report


def source_rows(spec: SourceSpec) -> Iterator[dict[str, Any]]:
    """Yield ``spec``'s parsed rows with its explicit edition stamped onto keyed rows.

    The single row source for :func:`run_pipeline` and the manifest import's pre-write
    checks, so both see exactly the same rows. Pre-parsed ``spec.rows`` are used as
    given; otherwise ``spec.path`` is parsed. Fail-closed ``_parse_failure`` markers pass
    through unstamped.
    """

    rows = spec.rows if spec.rows is not None else _PARSERS[spec.kind][0](spec.path)
    for raw in rows:
        yield raw if raw.get("_parse_failure") else stamp_edition(raw, spec)


def stamp_edition(raw: dict[str, Any], spec: SourceSpec) -> dict[str, Any]:
    """Stamp ``spec``'s explicit edition onto a parsed row, refusing a conflicting one.

    A manifest import names its edition explicitly, so ``valid_from`` and
    ``source_version`` come from the manifest, not from where the file lives. A row whose
    adapter already derived a different value (the ``analysenliste_YYYY-MM-DD`` filename
    convention) raises instead of silently choosing one. Specs without an explicit
    edition pass rows through unchanged.
    """

    explicit = {
        key: value
        for key, value in (("valid_from", spec.valid_from), ("source_version", spec.source_version))
        if value is not None
    }
    for key, value in explicit.items():
        parsed = raw.get(key)
        if parsed is not None and parsed != value:
            raise ValueError(
                f"{spec.path.name}: parsed {key} {parsed} conflicts with the "
                f"explicit edition {value}"
            )
    return {**raw, **explicit}
