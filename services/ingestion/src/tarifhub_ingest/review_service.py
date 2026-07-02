"""Human review write-back orchestration (deterministic, AI-free).

Applies one console ``approve`` / ``correct`` decision end-to-end: load the flagged
record, guard the decision, then run the SAME deterministic pipeline as ingest —
``validate`` -> ``freeze`` -> re-embed -> store the immutable successor version — and
append the audit event. Extracted from ``main.py`` so the HTTP route stays a thin
adapter (validate input, call the service, map the result) while this module owns the
orchestration; the pure decision logic and the console wire contract stay in
``review.py``.

The determinism boundary still covers the moved side effects:
``tests/test_value_path_boundary.py`` AST-scans EVERY module in this package (this one
included) and forbids LLM-client imports, while the frozen
``tests/test_review_boundary.py`` keeps pinning ``main.py`` and ``review.py``. The
intelligence on this path is the HUMAN, never an LLM.
"""

from __future__ import annotations

from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import Settings
from tarifhub_ingest.embeddings.embedder import get_embedder
from tarifhub_ingest.errors import (
    ReviewConflict,
    ReviewRecordNotFound,
    ReviewValidationError,
)
from tarifhub_ingest.review import (
    ReviewDecision,
    ReviewResult,
    prepare_reviewed_record,
    review_message,
)
from tarifhub_ingest.storage.tariff_repository import TariffRepository
from tarifhub_ingest.validators.tariff_validator import validate
from tarifhub_ingest.versioning.freeze_record import freeze


def apply_review_decision(
    decision: ReviewDecision,
    *,
    repo: TariffRepository,
    audit: AuditLogger,
    settings: Settings,
) -> ReviewResult:
    """Close the human-in-the-loop: a reviewed decision becomes a new frozen version.

    Loads the current flagged version, rejects any billing-field correction (400),
    applies the decision, then runs the SAME deterministic pipeline as ingest —
    ``validate`` (422 if the reviewed record is still invalid) then ``freeze`` — and
    persists an immutable new version (``version + 1``, new ``record_hash``) with an
    appended audit event. The prior version and the audit log are never rewritten.
    Failures raise domain exceptions (never a bare ``HTTPException``) for the
    registered problem+json handlers to render.
    """

    record = repo.get(decision.tariff_code, decision.tariff_system)
    if record is None:
        raise ReviewRecordNotFound(
            f"no record for system={decision.tariff_system.value} "
            f"code={decision.tariff_code}"
        )
    if not record.requires_review:
        raise ReviewConflict(
            f"record {decision.tariff_system.value}/{decision.tariff_code} "
            "is not flagged for review"
        )
    # Optimistic concurrency: if the client names a version, it must be the live one.
    if decision.record_hash and record.record_hash != decision.record_hash:
        raise ReviewConflict(
            "record_hash does not match the current flagged version (stale read)"
        )

    # A refused decision (billing/unknown-field correction) raises ReviewError, a domain
    # exception the registered handler renders as the same problem+json envelope (400).
    prepared = prepare_reviewed_record(record, decision)

    result = validate(prepared)
    if not result.ok:
        raise ReviewValidationError(
            "reviewed record fails validation", extra={"errors": result.errors}
        )

    frozen = freeze(prepared)
    # Re-embed exactly as the pipeline does so the corrected designation stays
    # searchable. The embedder is optional (None when skipped on the Postgres leg,
    # whose vector(1024) column rejects the 16-dim offline stub) — mirror the
    # pipeline's guard rather than assuming a vector.
    embedder = get_embedder(settings)
    embedding = None
    if embedder is not None:
        text = f"{frozen.tariff_system.value} {frozen.tariff_code} {frozen.designation.de}"
        embedding = embedder.embed(text)
    stored = repo.add(frozen, embedding=embedding)
    if not stored:
        raise ReviewConflict("this exact reviewed version already exists")

    # Re-read for the authoritative version the repository assigned (hash is stable).
    current = repo.get(decision.tariff_code, decision.tariff_system)
    assert current is not None  # just persisted

    corrected_fields = (
        sorted(decision.corrections or {}) if decision.action == "correct" else []
    )
    audit.log(
        event_type=f"review_{decision.action}",
        record=current,
        source_file="console-review",
        confidence=current.harmonization_confidence,
        validation_ok=result.ok,
        detail={
            "action": decision.action,
            "reviewer": decision.reviewer,
            "note": decision.note,
            "corrected_fields": corrected_fields,
            "prev_version": record.version,
            "prev_record_hash": record.record_hash,
        },
    )

    return ReviewResult(
        ok=True,
        tariff_system=current.tariff_system.value,
        tariff_code=current.tariff_code,
        action=decision.action,
        frozen=True,
        version=current.version,
        record_hash=current.record_hash,
        message=review_message(decision.action, current.version, corrected_fields),
    )
