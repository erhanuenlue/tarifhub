"""Deterministic, read-only comparison of two dated BAG AL editions (tariff system EAL).

Both editions come from the tracked manifest, never from per-code version numbers: their
documents are verified and their full lists parsed from the verified bytes, exactly as
:func:`import_manifest` does. The comparison reads the stored EAL history once, takes each
position's edition member by the import's own rule and classifies every position by
:data:`COMPARED_FIELDS` alone. Beside that classification it compares the published text of
selected German columns the frozen records do not carry (``bag_eal.TEXT_COLUMNS``, read with
their cell references from the same verified bytes) and lists each literal change once,
interpreting none; every other uncarried column is named in the result's scope limitation,
never compared. It never imports, initialises a database, writes an audit event or calls a
model; it reports frozen values and published texts and computes none.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

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
    "Only compared_fields classify positions, so unchanged means equal in every compared "
    "field. Of the workbook columns the frozen records do not carry, those in "
    "columns_compared_as_text are compared as published text under workbook_text, which "
    "never makes a position changed; the others (columns_not_compared) are not compared, and "
    "a change in them is not reported. The discipline flags count only through category, the "
    "first one marked Ja. Removed means listed in the earlier edition's verified full-list "
    "workbook and absent from the later one: not a legal repeal, a deleted record or a "
    "changed as_of result."
)

# What two texts may differ in and still be equal: Unicode NFC, and every run of whitespace
# read as one space with leading and trailing whitespace ignored. Nothing else.
TEXT_NORMALIZATION = ("unicode_nfc", "whitespace_folding")

_TEXT_SUMMARY = (
    "Texts of columns_compared on the German sheet of both verified full-list workbooks, for "
    "every position listed in both editions. Two texts are equal when they match after "
    "Unicode NFC normalization with each run of whitespace read as one space and leading and "
    "trailing whitespace ignored, so an empty or whitespace-only cell has no text; words, "
    "case, punctuation and digits count as written. from_text and to_text are the cells "
    "verbatim, null when a cell holds no value. A text change states what the cells say, not "
    "a changed rule or entitlement (interpretation none: Oui and Ja are different texts), and "
    "never makes a position changed; in_changed marks a position also listed under changed. "
    "A requested column an edition does not let the comparison read (not_comparable) is not "
    "compared and counts nowhere: coverage is complete when every requested column was "
    "compared, partial when some were, and unavailable when none was, and then nothing is "
    "counted or listed. Texts of added and removed positions, other columns and sheets, cell "
    "formatting and the PDFs are not compared."
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
    columns_compared_as_text: dict[str, tuple[str, ...]]  # under workbook_text, never a change
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


class TextChange(BaseModel):
    """One cell whose published text differs between the two editions (texts verbatim)."""

    model_config = _RESULT

    column: str
    from_cell: str
    to_cell: str
    from_text: str | None  # None: the cell holds no value
    to_text: str | None


class TextPosition(BaseModel):
    """A position listed in both editions with at least one text change, listed once."""

    model_config = _RESULT

    tariff_code: str
    in_changed: bool  # also listed under changed, for a compared field
    changes: tuple[TextChange, ...]


class UncomparableColumn(BaseModel):
    """A requested column one edition's workbook does not let the comparison read."""

    model_config = _RESULT

    column: str
    effective_date: date
    reason: Literal["missing", "repeated", "not_text"]
    cells: tuple[str, ...]  # repeated: the header cells naming it; not_text: the cells concerned


class TextHeader(BaseModel):
    """The header cell a compared column was read under, its text verbatim."""

    model_config = _RESULT

    column: str
    cell: str
    text: str


class TextSource(BaseModel):
    """Where an edition's texts were read: its verified full-list workbook, sheet and header."""

    model_config = _RESULT

    document: ManifestDocument
    sheet: str
    header_row: int
    headers: tuple[TextHeader, ...]  # one per compared column


class WorkbookText(BaseModel):
    """The published texts of selected German columns, compared beside the classification.

    ``counts``, ``cells_changed_by_column`` and ``positions`` are None when no requested
    column could be compared (coverage unavailable): nothing was compared, so nothing is
    counted as unchanged.
    """

    model_config = _RESULT

    summary: str
    interpretation: Literal["none"] = "none"
    normalization: tuple[str, ...] = TEXT_NORMALIZATION
    coverage: Literal["complete", "partial", "unavailable"]
    columns_requested: tuple[str, ...]
    columns_compared: tuple[str, ...]
    not_comparable: tuple[UncomparableColumn, ...]
    from_source: TextSource
    to_source: TextSource
    counts: dict[str, int] | None
    cells_changed_by_column: dict[str, int] | None
    positions: tuple[TextPosition, ...] | None


class EditionComparison(BaseModel):
    """Every position of two AL editions, each classified exactly once by compared_fields.

    ``unchanged`` lists the positions equal in every compared field; such a position may
    still have text changes, listed under ``workbook_text``. A change in any other workbook
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
    workbook_text: WorkbookText


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
        read = [_read_workbook(root, item) for item in (before, after)]
    except ManifestError as exc:
        raise EditionComparisonError(exc.problems) from None

    history = _eal_history(TariffRepository(conn, db))  # the one read of the stored rows
    codes = before.candidates.keys() | after.candidates.keys()
    problems = _history_problems({code: history[code] for code in sorted(codes & history.keys())})
    problems += _spellings(codes)
    (old, old_problems), (new, new_problems) = (_members(item, history) for item in (before, after))
    _refuse([*problems, *old_problems, *new_problems])

    changed, unchanged = [], []
    shared = sorted(old.keys() & new.keys())
    for code in shared:
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
    text = _workbook_text(
        (before, after), [cells for _, cells in read], shared, {p.tariff_code for p in changed}
    )
    return EditionComparison(
        from_edition=_edition(before),
        to_edition=_edition(after),
        scope_limitation=_scope([headers for headers, _ in read], text.columns_compared),
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
        workbook_text=text,
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


def _read_workbook(
    root: Path, item: _PreparedEdition
) -> tuple[dict[str, tuple[str, ...]], bag_eal.TextCells]:
    """The header rows and the German text cells of an edition's full list, both read from
    the same bytes, verified once more."""

    content, problems = _verify(root, item.document, keep=True)
    _refuse_if(problems)
    path = item.document.path
    try:
        return (
            bag_eal.column_headers(path, content=content),
            bag_eal.text_cells(path, content=content),
        )
    except Exception as exc:  # noqa: BLE001  as in _prepare_all, an unreadable workbook refuses
        raise ManifestError([f"{path}: {type(exc).__name__}: {exc}"]) from None


def _workbook_text(
    editions: tuple[_PreparedEdition, _PreparedEdition],
    read: list[bag_eal.TextCells],
    codes: list[str],
    changed: set[str],
) -> WorkbookText:
    """Every text change of the positions ``codes``, in the columns both editions can read;
    ``changed`` holds the positions listed under changed."""

    before, after = read
    requested = tuple(column.name for column in before.columns)
    compared = tuple(
        old.name
        for old, new in zip(before.columns, after.columns, strict=True)
        if old.readable and new.readable
    )
    positions = []
    for code in codes:
        old_cells, new_cells = before.rows[code], after.rows[code]
        changes = tuple(
            TextChange(
                column=name,
                from_cell=old_cells[name].cell,
                to_cell=new_cells[name].cell,
                from_text=old_cells[name].text,
                to_text=new_cells[name].text,
            )
            for name in compared
            if _folded(old_cells[name].text) != _folded(new_cells[name].text)
        )
        if changes:
            positions.append(
                TextPosition(tariff_code=code, in_changed=code in changed, changes=changes)
            )
    if compared == requested:
        coverage = "complete"
    elif compared:
        coverage = "partial"
    else:
        coverage = "unavailable"
    counts = by_column = listed = None  # no column compared: no count, not even of unchanged
    if compared:
        counts = {
            "positions_compared": len(codes),
            "positions_with_text_changes": len(positions),
            "positions_in_changed": sum(p.in_changed for p in positions),
            "cells_changed": sum(len(p.changes) for p in positions),
        }
        by_column = {
            name: sum(c.column == name for p in positions for c in p.changes) for name in compared
        }
        listed = tuple(positions)
    return WorkbookText(
        summary=_TEXT_SUMMARY,
        coverage=coverage,
        columns_requested=requested,
        columns_compared=compared,
        not_comparable=_not_comparable(editions, read),
        from_source=_text_source(editions[0], before, compared),
        to_source=_text_source(editions[1], after, compared),
        counts=counts,
        cells_changed_by_column=by_column,
        positions=listed,
    )


def _not_comparable(
    editions: tuple[_PreparedEdition, _PreparedEdition], read: list[bag_eal.TextCells]
) -> tuple[UncomparableColumn, ...]:
    """Each requested column an edition does not let the comparison read, with the reason."""

    found = []
    for columns in zip(*(cells.columns for cells in read), strict=True):
        for item, column in zip(editions, columns, strict=True):
            if not column.headers:
                reason, cells = "missing", ()
            elif len(column.headers) > 1:
                reason, cells = "repeated", tuple(header.cell for header in column.headers)
            elif column.not_text:
                reason, cells = "not_text", column.not_text
            else:
                continue
            found.append(
                UncomparableColumn(
                    column=column.name,
                    effective_date=item.edition.effective_date,
                    reason=reason,
                    cells=cells,
                )
            )
    return tuple(found)


def _folded(text: str | None) -> str:
    """``text`` as TEXT_NORMALIZATION compares it; a cell without text folds to ''."""

    return " ".join(unicodedata.normalize("NFC", text or "").split())


def _text_source(
    item: _PreparedEdition, read: bag_eal.TextCells, compared: tuple[str, ...]
) -> TextSource:
    return TextSource(
        document=item.document,
        sheet=read.sheet,
        header_row=read.header_row,
        headers=tuple(
            TextHeader(column=column.name, cell=column.headers[0].cell, text=column.headers[0].text)
            for column in read.columns
            if column.name in compared
        ),
    )


def _scope(columns: list[dict[str, tuple[str, ...]]], as_text: tuple[str, ...]) -> ScopeLimitation:
    """Sort both workbooks' columns into compared, category-only, text and not compared.

    ``as_text`` holds the German columns workbook_text compared, so a requested column that
    could not be compared stays listed as not compared.
    """

    compared: dict[str, tuple[str, ...]] = {}
    by_category: dict[str, tuple[str, ...]] = {}
    by_text: dict[str, tuple[str, ...]] = {}
    not_compared: dict[str, tuple[str, ...]] = {}
    for sheet, carried in bag_eal.CARRIED_COLUMNS.items():
        names: list[str] = []
        for headers in columns:  # both editions, first appearance kept, line breaks folded
            for header in headers.get(sheet, ()):
                name = " ".join(header.split())
                if name not in names:
                    names.append(name)
        category = bag_eal.CATEGORY_COLUMNS.get(sheet, ())
        text = as_text if sheet in bag_eal.TEXT_COLUMNS else ()
        compared[sheet] = tuple(n for n in names if n in carried)
        if category:
            by_category[sheet] = tuple(n for n in names if n in category)
        if sheet in bag_eal.TEXT_COLUMNS:
            by_text[sheet] = tuple(n for n in names if n in text)
        not_compared[sheet] = tuple(
            n for n in names if n not in carried and n not in category and n not in text
        )
    return ScopeLimitation(
        summary=_SCOPE_SUMMARY,
        columns_compared=compared,
        columns_compared_only_as_category=by_category,
        columns_compared_as_text=by_text,
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
