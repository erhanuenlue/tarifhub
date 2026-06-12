"""AI fill-reuse: carry forward a prior version's AI fills when source content is unchanged.

Live ``ai_map`` fills (designations, category) are NOT byte-stable across re-ingests, so a
re-run with a key re-versions filled records, and a re-run WITHOUT a key would re-version
them back to fill-less — both break re-ingest idempotency. This module makes the unchanged
case idempotent unconditionally: it strips a stored record back to its deterministic
pre-fill state and compares it (by content hash) against the freshly mapped candidate. When
they match, the source content has not changed, so the pipeline adopts the stored record's
content verbatim — its AI fills included — with NO model call, and freeze reproduces the
identical ``record_hash`` (the repository then dedupes).

Pure functions of their inputs; never mutate the stored record (we compare on copies). No
LLM imports — ``ai_map`` stays repo-free; this seam lives at the pipeline call site instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from tarifhub_ingest.models.tariff_model import Designation, TariffRecord, TariffSystem
from tarifhub_ingest.versioning.freeze_record import compute_record_hash

# The non-billing fields the AI seam may fill; metadata["ai_fields"] names which were.
_DESIGNATION_FILLS = {"designation_fr", "designation_it"}


def strip_to_prefill(stored: TariffRecord) -> TariffRecord:
    """Return a copy of ``stored`` with its AI fills reversed to the pre-fill state.

    Every field named in ``metadata["ai_fields"]`` is reset (designation.fr/it -> None
    inside a rebuilt Designation; category -> None), and the AI provenance keys are reset
    to the no-AI baseline (``ai_assisted`` False; ``ai_model`` / ``ai_status`` / ``ai_fields``
    dropped) while every other metadata key (mapper_version, source extras) is preserved.
    The scored fields ``harmonization_confidence`` / ``requires_review`` are reset to the
    model defaults too, because the comparison target is a fresh ``map_raw`` candidate
    (which is PRE-score) — scoring happens later in the pipeline, on whichever record wins.
    The result is byte-identical to what the deterministic ``map_raw`` produced before the
    fill, so its content hash equals a freshly mapped candidate's iff source content matches.
    ``stored`` is never mutated.
    """

    ai_fields = set(stored.metadata.get("ai_fields") or [])

    fr = None if "designation_fr" in ai_fields else stored.designation.fr
    it = None if "designation_it" in ai_fields else stored.designation.it
    designation = Designation(de=stored.designation.de, fr=fr, it=it)
    category = None if "category" in ai_fields else stored.category

    metadata = {
        k: v
        for k, v in stored.metadata.items()
        if k not in ("ai_assisted", "ai_model", "ai_status", "ai_fields")
    }
    metadata["ai_assisted"] = False

    defaults = TariffRecord.model_fields
    return stored.model_copy(
        update={
            "designation": designation,
            "category": category,
            "metadata": metadata,
            "harmonization_confidence": defaults["harmonization_confidence"].default,
            "requires_review": defaults["requires_review"].default,
        }
    )


def _adopt_content(candidate: TariffRecord, stored: TariffRecord) -> TariffRecord:
    """Adopt ``stored``'s hashed content + metadata onto a FRESH model instance.

    Carries every hashed field and metadata from ``stored`` (its AI fills included) but
    NOT ``record_hash`` / ``version`` / ``created_at`` — those are stamped fresh by freeze
    and the repository, exactly as for any other mapped record. Source/spec context
    (source_url) comes from ``candidate`` (the current run), not the old row.
    """

    return candidate.model_copy(
        update={
            "designation": Designation(
                de=stored.designation.de,
                fr=stored.designation.fr,
                it=stored.designation.it,
            ),
            "category": stored.category,
            "tax_points": stored.tax_points,
            "price_chf": stored.price_chf,
            "unit": stored.unit,
            "valid_from": stored.valid_from,
            "valid_to": stored.valid_to,
            "source_version": stored.source_version,
            "metadata": dict(stored.metadata),
        }
    )


@dataclass(frozen=True)
class ReuseOutcome:
    """The result of a reuse check at the pipeline ai_map call site."""

    record: TariffRecord
    reused: bool
    reused_from_version: int | None = None


def reuse_or_none(
    candidate: TariffRecord,
    repo,
    system: TariffSystem,
) -> ReuseOutcome | None:
    """Adopt the latest frozen version's content when source content is unchanged.

    Returns a :class:`ReuseOutcome` (reuse decided) or ``None`` (no reuse — the caller
    must run ``ai_map`` as today). ``candidate`` is the deterministic pre-fill ``map_raw``
    output for the current row. We look up the latest frozen ``(system, code)`` record,
    strip it to pre-fill, and compare content hashes. EQUAL -> adopt verbatim (no API
    call); NOT EQUAL / no previous version -> ``None``.
    """

    stored = repo.get(candidate.tariff_code, system)
    if stored is None:
        return None
    if compute_record_hash(strip_to_prefill(stored)) != compute_record_hash(candidate):
        return None
    return ReuseOutcome(
        record=_adopt_content(candidate, stored),
        reused=True,
        reused_from_version=stored.version,
    )
