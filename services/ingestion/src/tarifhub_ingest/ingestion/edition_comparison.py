"""Deterministic, read-only comparison of two dated BAG AL editions (tariff system EAL).

Both editions come from the tracked manifest, never from per-code version numbers: their
documents are verified and their full lists parsed from the verified bytes, exactly as
:func:`import_manifest` does. The comparison reads the stored EAL history once, takes each
position's edition member by the import's own rule and classifies every position by
:data:`COMPARED_FIELDS` alone: workbook columns the frozen records do not carry are named in
the result's scope limitation, never compared. It never imports, initialises a database,
writes an audit event or calls a model; it reports frozen values and computes none.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tarifhub_ingest.adapters import bag_eal
from tarifhub_ingest.ingestion.manifest import (
    ManifestDocument,
    ManifestError,
    _eal_history,
    _history_problems,
    _load,
    _match_stored,
    _PreparedEdition,
    _prepare_all,
    _refuse_if,
    _verify,
)
from tarifhub_ingest.models.tariff_model import TariffRecord
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository

# The source fields a frozen AL record carries, sorted; designation leaves are dotted as in
# the serving diff. Everything else in the record is edition, provenance or pipeline data.
COMPARED_FIELDS = (
    "category",
    "designation.de",
    "designation.fr",
    "designation.it",
    "price_chf",
    "tax_points",
    "unit",
)

_SCOPE_SUMMARY = (
    "Only compared_fields are compared, so unchanged means equal in every compared field. "
    "Workbook columns the frozen records do not carry (columns_not_compared) are not "
    "compared, and a change in them is not reported; the discipline flags count only "
    "through category, the first one marked Ja. Removed means listed in the earlier "
    "edition's verified full-list workbook and absent from the later one: not a legal "
    "repeal, a deleted record or a changed as_of result."
)

_PLAIN_NUMBER = re.compile(r"\d+(?:\.\d+)?")  # an AL position number: 4700, 1024.1, 1099.11

_RESULT = ConfigDict(extra="forbid", frozen=True)


class EditionComparisonError(ValueError):
    """The manifest, the two editions or the stored EAL history make the comparison unsafe."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__(
            "edition comparison refused:\n" + "\n".join(f"- {p}" for p in self.problems)
        )


class ScopeLimitation(BaseModel):
    """What the comparison can see: workbook columns by sheet, read from both verified files."""

    model_config = _RESULT

    summary: str
    columns_compared: dict[str, tuple[str, ...]]
    columns_compared_only_as_category: dict[str, tuple[str, ...]]
    columns_not_compared: dict[str, tuple[str, ...]]


class EditionReference(BaseModel):
    """One compared edition: its manifest date, its stored label and its listed documents."""

    model_config = _RESULT

    effective_date: date
    source_version: str
    positions: int  # positions in the edition's verified full-list workbook
    documents: tuple[ManifestDocument, ...]


class RecordReference(BaseModel):
    """The frozen record that is an edition's member for a position.

    The member is the earliest stored version of the edition's date, the one the import
    froze from the workbook. Later versions of that date (a review correction, an AI
    re-fill) stay current for as_of; they are cited here, never compared in its place.
    """

    model_config = _RESULT

    version: int
    record_hash: str
    successor_versions: tuple[int, ...] = ()


class FieldChange(BaseModel):
    """One compared field whose value differs between the two editions (values verbatim)."""

    model_config = _RESULT

    field: str
    from_value: str | None
    to_value: str | None


class ListedPosition(BaseModel):
    """A position listed in only one of the two editions, with its compared values."""

    model_config = _RESULT

    tariff_code: str
    record: RecordReference
    values: dict[str, str | None]


class ChangedPosition(BaseModel):
    """A position listed in both editions with a different value in a compared field."""

    model_config = _RESULT

    tariff_code: str
    from_record: RecordReference
    to_record: RecordReference
    changes: tuple[FieldChange, ...]


class EditionComparison(BaseModel):
    """Every position of two AL editions, each classified exactly once by compared_fields.

    ``unchanged`` lists the positions equal in every compared field; a change in a workbook
    column the records do not carry (``scope_limitation``) is not seen, so this is not the
    list of every change BAG published.
    """

    model_config = _RESULT

    from_edition: EditionReference
    to_edition: EditionReference
    compared_fields: tuple[str, ...] = COMPARED_FIELDS
    scope_limitation: ScopeLimitation
    counts: dict[str, int]  # added, removed, changed and unchanged, in that order
    added: tuple[ListedPosition, ...]
    removed: tuple[ListedPosition, ...]
    changed: tuple[ChangedPosition, ...]
    unchanged: tuple[str, ...]


def compare_editions(
    manifest_path: str | Path,
    conn,
    db: Database,
    *,
    from_date: date,
    to_date: date,
) -> EditionComparison:
    """Compare the manifest editions ``from_date`` and ``to_date`` as stored on ``conn``.

    Read-only on ``conn``. Raises :class:`EditionComparisonError`, listing every problem,
    unless both editions are listed in date order, their documents match their SHA-256,
    each stored edition equals its verified full list (complete, same content, nothing
    extra), the stored history of their positions is consistent, no position number is
    written two ways, and every member value is the workbook's own (no scale overflow, no
    AI fill).
    """

    try:  # the import's own checks; their refusals become this comparison's
        manifest, root = _load(Path(manifest_path))
        editions = {edition.effective_date: edition for edition in manifest.editions}
        problems = [
            f"edition {day} is not listed in the manifest"
            for day in dict.fromkeys((from_date, to_date))
            if day not in editions
        ]
        if from_date >= to_date:
            problems.append(
                f"the earlier edition comes first: {from_date} is not before {to_date}"
            )
        _refuse(problems)
        selected = manifest.model_copy(
            update={
                "editions": (editions[from_date], editions[to_date]),
                "supporting_documents": (),
            }
        )
        before, after = _prepare_all(selected, root)  # verified, parsed and mapped
        columns = [_workbook_columns(root, item) for item in (before, after)]
    except ManifestError as exc:
        raise EditionComparisonError(exc.problems) from None

    history = _eal_history(TariffRepository(conn, db))  # the one read of the stored rows
    codes = before.candidates.keys() | after.candidates.keys()
    problems = _history_problems({code: history[code] for code in sorted(codes & history.keys())})
    problems += _spellings(codes)
    (old, old_problems), (new, new_problems) = (_members(item, history) for item in (before, after))
    _refuse([*problems, *old_problems, *new_problems])

    changed, unchanged = [], []
    for code in sorted(old.keys() & new.keys()):
        old_values, new_values = _values(old[code][0]), _values(new[code][0])
        changes = tuple(
            FieldChange(field=name, from_value=old_values[name], to_value=new_values[name])
            for name in COMPARED_FIELDS
            if old_values[name] != new_values[name]
        )
        if changes:
            changed.append(
                ChangedPosition(
                    tariff_code=code,
                    from_record=_reference(old[code]),
                    to_record=_reference(new[code]),
                    changes=changes,
                )
            )
        else:
            unchanged.append(code)
    added = _listed(new, sorted(new.keys() - old.keys()))
    removed = _listed(old, sorted(old.keys() - new.keys()))
    return EditionComparison(
        from_edition=_edition(before),
        to_edition=_edition(after),
        scope_limitation=_scope(columns),
        counts={
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(unchanged),
        },
        added=added,
        removed=removed,
        changed=tuple(changed),
        unchanged=tuple(unchanged),
    )


def _members(
    item: _PreparedEdition, history: dict[str, list[TariffRecord]]
) -> tuple[dict[str, list[TariffRecord]], list[str]]:
    """Each file position's stored versions of the edition's date, the member first.

    Returned with every problem that rules out comparing this edition. Which version is the
    member is the import's own rule (:func:`_match_stored`).
    """

    effective = item.edition.effective_date
    versions, missing, conflicting, unlisted = _match_stored(item, history)
    problems = []
    if missing:
        problems.append(
            f"edition {effective}: {len(missing)} of {len(item.candidates)} position(s) of its "
            f"full list are not stored (e.g. {', '.join(sorted(missing)[:5])}); a partly stored "
            "edition cannot tell a removed position from an unfinished import, so import it "
            "with --manifest first"
        )
    if conflicting:
        problems.append(
            f"edition {effective}: {len(conflicting)} stored position(s) differ from its full "
            f"list (e.g. {', '.join(sorted(conflicting)[:5])}); the stored edition does not "
            "match the file"
        )
    if unlisted:
        problems.append(
            f"edition {effective}: {len(unlisted)} stored position(s) of that date are not in "
            f"its full list (e.g. {', '.join(unlisted[:5])}); the stored edition does not match "
            "the file"
        )
    members = {code: found[0] for code, found in versions.items() if found}
    beyond_scale = sorted(  # the mapper's raw_<field> marker: the value did not fit the scale
        (code, key.removeprefix("raw_"))
        for code, member in members.items()
        for key in member.metadata
        if key.startswith("raw_")
    )
    if beyond_scale:
        problems.append(
            f"edition {effective}: {len({code for code, _ in beyond_scale})} position(s) hold a "
            "value the canonical scale could not store exactly (e.g. "
            f"{', '.join(f'{code}: {name}' for code, name in beyond_scale[:5])}); the stored "
            "value is not the workbook's"
        )
    ai_filled = sorted(
        (code, name)
        for code, member in members.items()
        for name in member.metadata.get("ai_fields") or ()
    )
    if ai_filled:
        problems.append(
            f"edition {effective}: {len({code for code, _ in ai_filled})} position(s) carry "
            "AI-filled fields (e.g. "
            f"{', '.join(f'{code}: {name}' for code, name in ai_filled[:5])}); an AI fill is "
            "not a workbook value"
        )
    return versions, problems


def _spellings(codes: Iterable[str]) -> list[str]:
    """Position numbers written more than one way (``1000`` and ``1000.00``) across editions.

    Positions join by their exact code, so a code written differently in the later file would
    look removed and added. Only detected, never aliased: the codes stay as the files give them.
    """

    by_number: dict[Decimal, list[str]] = defaultdict(list)
    for code in sorted(codes):
        if _PLAIN_NUMBER.fullmatch(code):
            by_number[Decimal(code)].append(code)
    clashes = [" and ".join(spellings) for spellings in by_number.values() if len(spellings) > 1]
    if not clashes:
        return []
    return [
        f"{len(clashes)} position number(s) are written more than one way across the two "
        f"editions (e.g. {'; '.join(clashes[:5])}); positions join by their exact code, so a "
        "rewritten code would look removed and added"
    ]


def _refuse(problems: Iterable[str]) -> None:
    """Raise one :class:`EditionComparisonError` listing every problem."""

    found = tuple(problems)
    if found:
        raise EditionComparisonError(found)


def _workbook_columns(root: Path, item: _PreparedEdition) -> dict[str, tuple[str, ...]]:
    """The header rows of an edition's full list, read from bytes verified once more."""

    content, problems = _verify(root, item.document, keep=True)
    _refuse_if(problems)
    return bag_eal.column_headers(item.document.path, content=content)


def _scope(columns: list[dict[str, tuple[str, ...]]]) -> ScopeLimitation:
    """Sort both workbooks' columns into compared, category-only and not compared."""

    compared: dict[str, tuple[str, ...]] = {}
    by_category: dict[str, tuple[str, ...]] = {}
    not_compared: dict[str, tuple[str, ...]] = {}
    for sheet, carried in bag_eal.CARRIED_COLUMNS.items():
        names: list[str] = []
        for headers in columns:  # both editions, first appearance kept, line breaks folded
            for header in headers.get(sheet, ()):
                name = " ".join(header.split())
                if name not in names:
                    names.append(name)
        category = bag_eal.CATEGORY_COLUMNS.get(sheet, ())
        compared[sheet] = tuple(n for n in names if n in carried)
        if category:
            by_category[sheet] = tuple(n for n in names if n in category)
        not_compared[sheet] = tuple(n for n in names if n not in carried and n not in category)
    return ScopeLimitation(
        summary=_SCOPE_SUMMARY,
        columns_compared=compared,
        columns_compared_only_as_category=by_category,
        columns_not_compared=not_compared,
    )


def _edition(item: _PreparedEdition) -> EditionReference:
    return EditionReference(
        effective_date=item.edition.effective_date,
        source_version=item.spec.source_version,
        positions=len(item.candidates),
        documents=item.edition.documents,
    )


def _listed(
    members: dict[str, list[TariffRecord]], codes: list[str]
) -> tuple[ListedPosition, ...]:
    return tuple(
        ListedPosition(
            tariff_code=code, record=_reference(members[code]), values=_values(members[code][0])
        )
        for code in codes
    )


def _reference(versions: list[TariffRecord]) -> RecordReference:
    """The member (the earliest version of its edition's date) and its later successors."""

    member, *successors = versions
    return RecordReference(
        version=member.version,
        record_hash=member.record_hash,
        successor_versions=tuple(v.version for v in successors),
    )


def _values(record: TariffRecord) -> dict[str, str | None]:
    """The compared fields of ``record``, decimals in the canonical form the hash uses."""

    return {
        "category": record.category,
        "designation.de": record.designation.de,
        "designation.fr": record.designation.fr,
        "designation.it": record.designation.it,
        "price_chf": _decimal_text(record.price_chf),
        "tax_points": _decimal_text(record.tax_points),
        "unit": record.unit,
    }


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")
