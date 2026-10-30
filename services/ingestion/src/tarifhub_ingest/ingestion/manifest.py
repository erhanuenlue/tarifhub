"""Manifest-driven import of dated BAG Analysenliste editions (tariff system EAL).

A tracked manifest (``data/manifests/bag-al.json``) lists each AL edition under its
effective date, with the downloaded documents, their SHA-256 hashes and BAG download
URLs. Only an edition's ``full_list_xlsx`` enters the tariff pipeline; the PDFs are
supporting sources for later explanation work and are never imported.

Editions import oldest first through the unchanged :func:`run_pipeline`, all of them in
one transaction: the batch is stored whole or not at all. The manifest supplies
``valid_from`` and the deterministic ``source_version`` before freeze, so a record's
identity never depends on the file's local name or location. Records keep the generic
BAG page as ``source_url``; the exact download URL stays in the manifest.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from tarifhub_ingest.adapters import bag_eal
from tarifhub_ingest.audit.audit_logger import AuditLogger
from tarifhub_ingest.config import Settings
from tarifhub_ingest.embeddings.embedder import Embedder
from tarifhub_ingest.ingestion.fill_reuse import matches_prefill
from tarifhub_ingest.ingestion.pipeline import PipelineReport, run_pipeline, source_rows
from tarifhub_ingest.ingestion.source_loader import EAL_SOURCE_URL, SourceSpec
from tarifhub_ingest.mappers.tariff_mapper import map_raw
from tarifhub_ingest.models.tariff_model import TariffRecord, TariffSystem
from tarifhub_ingest.storage.db import Database
from tarifhub_ingest.storage.tariff_repository import TariffRepository

DocumentKind = Literal[
    "full_list_xlsx", "full_list_pdf", "amendment_pdf", "commentary_pdf", "handbook_pdf"
]
_TARIFF_LIST: DocumentKind = "full_list_xlsx"
_CHUNK = 64 * 1024
_MAX_MANIFEST_BYTES = 1024 * 1024  # a manifest is a few KB; refuse anything wildly larger
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Fields every stored version of one edition shares: post-freeze successors (a review
# correction, an AI re-fill) may change only non-billing fields such as designations.
_EDITION_FIELDS = (
    "tax_points", "price_chf", "valid_from", "valid_to", "source_version", "source_url"
)


class ManifestError(ValueError):
    """The manifest, the selected batch or the stored EAL history makes the import unsafe.

    Raised before the first write, except for the end-of-run history check, whose writes
    the import's transaction then rolls back.
    """

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__(
            "manifest import refused:\n" + "\n".join(f"- {problem}" for problem in self.problems)
        )


# Strict JSON parsing: no coercion (a numeric date is not a date), no unknown fields.
_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True)


class ManifestDocument(BaseModel):
    """One downloaded BAG document, identified by its repository path and SHA-256."""

    model_config = _STRICT

    kind: DocumentKind
    path: str
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    source_url: str | None = None

    @field_validator("path")
    @classmethod
    def _repository_relative(cls, value: str) -> str:
        """A plain repository-relative POSIX path in NFC, without control characters."""

        if "\\" in value or ":" in value or any(s in ("", ".", "..") for s in value.split("/")):
            raise ValueError("must be a repository-relative POSIX path without '.' or '..'")
        if not unicodedata.is_normalized("NFC", value) or any(
            unicodedata.category(ch).startswith("C") for ch in value
        ):
            raise ValueError("must be NFC-normalised text without control characters")
        return value

    @field_validator("source_url")
    @classmethod
    def _bag_download(cls, value: str | None) -> str | None:
        """The adapter's fetch() pin (https on bag.admin.ch), as a plain public link."""

        if value is not None:
            parts = urlsplit(value)
            host = (parts.hostname or "").lower()
            plain = not (parts.username or parts.password or parts.query or parts.fragment)
            if (
                parts.scheme != "https"
                or not (host == "bag.admin.ch" or host.endswith(".bag.admin.ch"))
                or "\\" in value
                or not plain
                or any(unicodedata.category(ch).startswith("C") for ch in value)
            ):
                raise ValueError(
                    "must be an https URL on bag.admin.ch without credentials, query or fragment"
                )
        return value


class ManifestEdition(BaseModel):
    """One AL edition: its effective date and the documents published for it."""

    model_config = _STRICT

    effective_date: date
    documents: tuple[ManifestDocument, ...]

    @field_validator("effective_date", mode="before")
    @classmethod
    def _iso_date(cls, value: Any) -> Any:
        """Only a YYYY-MM-DD string, never a timestamp in any form."""

        if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
            raise ValueError("must be an ISO date YYYY-MM-DD")
        return date.fromisoformat(value)  # strict mode then sees a real date

    @model_validator(mode="after")
    def _one_tariff_list(self) -> ManifestEdition:
        """An edition imports exactly one full tariff list; PDFs only support it."""

        count = sum(1 for d in self.documents if d.kind == _TARIFF_LIST)
        if count != 1:
            raise ValueError(
                f"edition {self.effective_date} must list exactly one {_TARIFF_LIST}, "
                f"found {count}"
            )
        return self

    @property
    def tariff_list(self) -> ManifestDocument:
        """The edition's single importable document."""

        return next(d for d in self.documents if d.kind == _TARIFF_LIST)


class Manifest(BaseModel):
    """The whole manifest file: dated editions plus undated supporting documents."""

    model_config = _STRICT

    manifest_version: Literal[1]
    tariff_system: Literal["EAL"]
    editions: tuple[ManifestEdition, ...]
    supporting_documents: tuple[ManifestDocument, ...] = ()

    @field_validator("manifest_version", mode="before")
    @classmethod
    def _integer_version(cls, value: Any) -> Any:
        """JSON ``true`` and ``1.0`` equal 1 in Python but are not version 1."""

        if type(value) is not int:
            raise ValueError("must be the integer 1")
        return value

    @model_validator(mode="after")
    def _no_duplicates(self) -> Manifest:
        """Each edition date, document path and file hash appears once in the manifest.

        Paths compare case-insensitively, since a case-insensitive file system (the
        macOS default) maps both spellings to one file.
        """

        documents = [d for e in self.editions for d in e.documents]
        documents += self.supporting_documents
        problems = [] if self.editions else ["editions is empty; a manifest lists at least one"]
        for label, values in (
            ("edition effective_date", [e.effective_date.isoformat() for e in self.editions]),
            ("document path", [d.path.casefold() for d in documents]),
            ("document sha256", [d.sha256 for d in documents]),
        ):
            repeated = sorted(v for v, n in Counter(values).items() if n > 1)
            if repeated:
                problems.append(f"{label} {', '.join(repeated)} appears more than once")
        if any(d.kind == _TARIFF_LIST for d in self.supporting_documents):
            problems.append(
                f"supporting_documents cannot hold a {_TARIFF_LIST}; tariff lists belong "
                "to an edition"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self


@dataclass(frozen=True)
class EditionOutcome:
    """What the import did with one manifest edition."""

    effective_date: date
    source_version: str
    path: str
    action: Literal["imported", "already_present"]
    already_stored: int  # positions of this edition that were stored before the run
    report: PipelineReport | None = None


@dataclass(frozen=True)
class ManifestImportReport:
    """Per-edition outcomes, oldest edition first."""

    editions: tuple[EditionOutcome, ...]


@dataclass(frozen=True)
class _PreparedEdition:
    """A selected edition ready to import: its pipeline spec and pre-fill candidates."""

    edition: ManifestEdition
    document: ManifestDocument
    spec: SourceSpec
    candidates: dict[str, TariffRecord]  # tariff_code -> map_raw output (pre-fill)
    keyed_rows: tuple[tuple[str, dict[str, Any]], ...]  # (tariff_code, parsed row), in order

    def outcome(self, codes: tuple[str, ...], report: PipelineReport | None) -> EditionOutcome:
        """Describe what the import did with this edition, given the codes it imported."""

        return EditionOutcome(
            effective_date=self.edition.effective_date,
            source_version=self.spec.source_version,
            path=self.document.path,
            action="imported" if codes else "already_present",
            already_stored=len(self.candidates) - len(codes),
            report=report,
        )


def import_manifest(
    manifest_path: str | Path,
    conn,
    db: Database,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
) -> ManifestImportReport:
    """Import the manifest's AL editions oldest first, as one transaction on ``conn``.

    Every check runs before the first write. The run ends by planning again against the
    stored history: every position must now be present, and every planning rule must
    still hold, so a competing writer that slipped in after planning raises instead of
    passing silently. The import commits once, after the last edition; a refusal or any
    failure rolls the whole batch back, tariff rows and audit events alike. Should the
    rollback itself fail, the connection is closed, which discards the batch too. ``conn``
    must hold no uncommitted writes of the caller's: they would share that fate.
    """

    batch = _BatchConnection(conn)
    repo, audit = TariffRepository(batch, db), AuditLogger(batch, db)
    try:
        report = _import(Path(manifest_path), repo, audit, settings=settings, embedder=embedder)
        conn.commit()
    except BaseException as exc:
        try:
            conn.rollback()  # no partial edition, nor a failed commit's batch left pending
        except BaseException as failure:  # noqa: BLE001  closing instead; exc is raised
            conn.close()  # discards whatever the failed rollback left pending
            exc.add_note(f"the rollback failed ({failure!r}), so the connection was closed")
        raise
    return report


class _BatchConnection:
    """A connection whose commits wait for the end of the manifest import.

    The repository and the audit logger commit after every row; deferring those commits
    makes the whole import one transaction, which :func:`import_manifest` commits or
    rolls back.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, *args, **kwargs):
        """Run a statement on the real connection, inside the open batch."""

        return self._conn.execute(*args, **kwargs)

    def commit(self) -> None:
        """Deferred: the batch commits once, after the whole import succeeded."""


def _import(
    manifest_path: Path,
    repo: TariffRepository,
    audit: AuditLogger,
    *,
    settings: Settings | None,
    embedder: Embedder | None,
) -> ManifestImportReport:
    """Check, plan and import the batch through ``repo`` and ``audit`` (no commit here)."""

    manifest, root = _load(manifest_path)
    prepared = _prepare_all(manifest, root)
    plans = _plan(prepared, _eal_history(repo))

    outcomes: list[EditionOutcome] = []
    for item, codes in zip(prepared, plans, strict=True):
        report = None
        if codes:
            wanted = set(codes)
            rows = tuple(raw for code, raw in item.keyed_rows if code in wanted)
            spec = replace(item.spec, rows=rows)
            report = run_pipeline([spec], repo, audit, settings=settings, embedder=embedder)
        outcomes.append(item.outcome(codes, report))

    try:
        leftover = [code for codes in _plan(prepared, _eal_history(repo)) for code in codes]
    except ManifestError as exc:
        late = list(exc.problems)
    else:
        late = [f"{len(leftover)} position(s) still missing after the import"] if leftover else []
    _refuse_if(
        f"stored EAL history changed during the import (a concurrent writer?): {problem}"
        for problem in late
    )
    return ManifestImportReport(editions=tuple(outcomes))


def _refuse_if(problems: Iterable[str]) -> None:
    """Raise one :class:`ManifestError` listing every problem, before any write."""

    found = tuple(problems)
    if found:
        raise ManifestError(found)


def _load(manifest_path: Path) -> tuple[Manifest, Path]:
    """Parse the manifest strictly and return it with its repository root.

    Document paths are repository-relative, so the manifest must sit in
    ``<repository>/data/manifests/``; the root is two levels above that folder.
    """

    try:
        path = manifest_path.resolve()
        if path.parent.name != "manifests" or path.parent.parent.name != "data":
            raise ManifestError(
                [f"{manifest_path}: a manifest must live in <repository>/data/manifests/"]
            )
        if not path.is_file():
            raise ManifestError([f"{manifest_path}: manifest not found"])
    except (OSError, RuntimeError) as exc:  # a symlink loop, an unsearchable folder
        raise ManifestError([f"{manifest_path}: {type(exc).__name__}"]) from None
    try:
        with open(path, "rb") as handle:
            data = handle.read(_MAX_MANIFEST_BYTES + 1)
    except OSError as exc:  # unreadable (permissions, I/O): a refusal, never a crash
        raise ManifestError([f"{manifest_path}: {type(exc).__name__}"]) from None
    if len(data) > _MAX_MANIFEST_BYTES:
        raise ManifestError([f"{manifest_path}: larger than the {_MAX_MANIFEST_BYTES}-byte limit"])
    try:  # the schema keeps the last of two equal keys, so refuse duplicates first
        json.loads(data, object_pairs_hook=_refuse_duplicate_keys)
    except (ValueError, RecursionError) as exc:
        message = str(exc) if isinstance(exc, _DuplicateKey) else f"Invalid JSON: {exc}"
        raise ManifestError([f"manifest: {message[:200]}"]) from None
    try:
        manifest = Manifest.model_validate_json(data)
    except ValidationError as exc:
        raise ManifestError(
            f"{'.'.join(str(p)[:80] for p in err['loc']) or 'manifest'}: {err['msg'][:200]}"
            for err in exc.errors()
        ) from None
    return manifest, path.parents[2]


class _DuplicateKey(ValueError):
    """A JSON object repeats a key."""


def _refuse_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    repeated = sorted(key for key, n in Counter(key for key, _ in pairs).items() if n > 1)
    if repeated:
        raise _DuplicateKey(f"duplicate key {', '.join(repr(k[:80]) for k in repeated)}")
    return dict(pairs)


def _locate(root: Path, relative: str) -> tuple[Path | None, str | None]:
    """Find a manifest path under ``root``, matching each component by its NFC form.

    Manifest paths are NFC, but a file saved on macOS can carry the same name in NFD, which
    a byte-exact file system (Linux) does not match. Each component is looked up among its
    folder's entries by NFC equality, the same way on every file system (so case must match
    too); entries whose names differ only in normalisation are ambiguous and refused.
    """

    path = root
    for part in relative.split("/"):
        try:
            matches = [e for e in path.iterdir() if unicodedata.normalize("NFC", e.name) == part]
        except (FileNotFoundError, NotADirectoryError):
            return None, "file not found"
        except OSError as exc:  # an unreadable folder: a problem, never a crash
            return None, type(exc).__name__
        if len(matches) > 1:
            return None, f"{len(matches)} entries differ only in Unicode normalisation; keep one"
        if not matches:
            return None, "file not found"
        path = matches[0]
    return path, None


def _verify(
    root: Path, document: ManifestDocument, *, keep: bool
) -> tuple[bytes | None, list[str]]:
    """Check one listed document: found (see :func:`_locate`), inside the root once links
    are resolved, a file, and carrying its SHA-256.

    With ``keep`` the verified bytes are returned too (capped at the adapter's size
    limit), so they are the very bytes that get parsed and frozen; nothing re-reads the
    file later. Other documents are hashed in a stream and never parsed.
    """

    located, problem = _locate(root, document.path)
    if located is None:
        return None, [f"{document.path}: {problem}"]
    try:
        path = located.resolve()
        if not path.is_relative_to(root):
            return None, [f"{document.path}: resolves outside the repository root"]
        if not path.is_file():
            return None, [f"{document.path}: file not found"]
    except (OSError, RuntimeError) as exc:  # a symlink loop, an unsearchable folder
        return None, [f"{document.path}: {type(exc).__name__}"]
    digest = hashlib.sha256()
    kept: list[bytes] = []
    size = 0
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                digest.update(chunk)
                if keep:
                    size += len(chunk)
                    if size > bag_eal._MAX_BYTES:  # the adapter's own workbook size limit
                        return None, [f"{document.path}: larger than {bag_eal._MAX_BYTES} bytes"]
                    kept.append(chunk)
    except OSError as exc:  # unreadable (permissions, I/O): a problem, never a crash
        return None, [f"{document.path}: {type(exc).__name__}"]
    actual = digest.hexdigest()
    if actual != document.sha256:
        return None, [
            f"{document.path}: sha256 mismatch "
            f"(manifest {document.sha256[:12]}..., file {actual[:12]}...)"
        ]
    return (b"".join(kept) if keep else None), []


def _prepare_all(manifest: Manifest, root: Path) -> list[_PreparedEdition]:
    """Verify every listed document, then parse and map each edition's tariff list.

    Editions come back oldest first. Any problem anywhere (a document outside the root,
    missing, or off its hash; a workbook that cannot be parsed or holds no positions;
    a conflicting filename date) refuses the whole batch before any write.
    """

    problems = [p for d in manifest.supporting_documents for p in _verify(root, d, keep=False)[1]]
    prepared: list[_PreparedEdition] = []
    for edition in sorted(manifest.editions, key=lambda e: e.effective_date):
        content = None
        for document in edition.documents:
            data, found = _verify(root, document, keep=document.kind == _TARIFF_LIST)
            problems += found
            if document.kind == _TARIFF_LIST:
                content = data
        if content is None:
            continue  # its problem is already listed
        try:
            item = _prepare(edition, content)
        except Exception as exc:  # noqa: BLE001  an unreadable workbook refuses the batch
            problems.append(f"{edition.tariff_list.path}: {type(exc).__name__}: {exc}")
            continue
        if not item.candidates:  # an empty or truncated download is not an edition
            problems.append(f"{edition.tariff_list.path}: contains no tariff positions")
        prepared.append(item)
    _refuse_if(problems)
    return prepared


def _prepare(edition: ManifestEdition, content: bytes) -> _PreparedEdition:
    """Parse the verified bytes once and map them exactly as the pipeline will.

    The parsed rows ride on the spec, so the pipeline freezes these rows rather than
    re-reading the file; the spec's path is the repository-relative manifest path.
    """

    document = edition.tariff_list
    spec = SourceSpec(
        system=TariffSystem.EAL,
        kind="bag_eal",
        path=Path(document.path),
        source_url=EAL_SOURCE_URL,
        valid_from=edition.effective_date,
        source_version=bag_eal.source_version_for(edition.effective_date),
        rows=tuple(bag_eal.parse(document.path, content=content)),
    )
    candidates: dict[str, TariffRecord] = {}
    keyed_rows: list[tuple[str, dict[str, Any]]] = []
    for raw, stamped in zip(spec.rows, source_rows(spec), strict=True):
        if stamped.get("_parse_failure"):
            continue  # never mapped or frozen by the pipeline either
        record = map_raw(stamped, system=spec.system, source_url=spec.source_url)
        candidates[record.tariff_code] = record
        keyed_rows.append((record.tariff_code, raw))
    return _PreparedEdition(
        edition=edition,
        document=document,
        spec=spec,
        candidates=candidates,
        keyed_rows=tuple(keyed_rows),
    )


def _eal_history(repo: TariffRepository) -> dict[str, list[TariffRecord]]:
    """Existing EAL versions by position code, lowest version first."""

    history: dict[str, list[TariffRecord]] = defaultdict(list)
    for record in repo.list_by_system(TariffSystem.EAL):  # ordered by code, version
        history[record.tariff_code].append(record)
    return history


def _plan(
    prepared: list[_PreparedEdition], history: dict[str, list[TariffRecord]]
) -> list[tuple[str, ...]]:
    """Decide, per edition, which positions to import, before any write.

    A position is already present when its earliest stored version of this edition's
    date has this edition's content; later same-dated versions are post-freeze
    successors (a review correction, an AI re-fill) and stay current. Every other
    position is imported, and must be newer than everything stored for it: the
    repository appends at MAX(version) + 1 and as_of picks the highest qualifying
    version, so an older edition would silently become current. Earlier editions of the
    same batch count as stored once planned.
    """

    batch = {code for item in prepared for code in item.candidates}
    _refuse_if(_history_problems({code: history[code] for code in sorted(batch & history.keys())}))

    known = {code: list(versions) for code, versions in history.items()}
    plans: list[tuple[str, ...]] = []
    problems: list[str] = []
    for item in prepared:
        effective = item.edition.effective_date
        _, missing, conflicting, unlisted = _match_stored(item, known)
        newer = sorted(
            code for code in missing if any(v.valid_from > effective for v in known.get(code, ()))
        )
        if conflicting:
            problems.append(
                f"edition {effective}: {len(conflicting)} position(s) already have a "
                f"{effective} version with different content (e.g. "
                f"{', '.join(sorted(conflicting)[:5])}); the stored edition does not match "
                "this manifest's file."
            )
        if unlisted:
            problems.append(
                f"edition {effective}: the stored {effective} edition has {len(unlisted)} "
                f"position(s) this manifest's file does not list (e.g. "
                f"{', '.join(unlisted[:5])}); the stored edition does not match the file."
            )
        if newer:
            later = {v.valid_from for c in newer for v in known[c] if v.valid_from > effective}
            dates = sorted(d.isoformat() for d in later)
            problems.append(
                f"edition {effective}: {len(newer)} position(s) already have a newer EAL "
                f"edition {', '.join(dates)} (e.g. {', '.join(newer[:5])}); importing it now "
                "would make the older edition current. Import editions oldest first, into "
                "a database without newer EAL editions."
            )
        plans.append(tuple(missing))
        for code in missing:
            known.setdefault(code, []).append(item.candidates[code])
    _refuse_if(problems)
    return plans


def _match_stored(
    item: _PreparedEdition, versions_by_code: dict[str, list[TariffRecord]]
) -> tuple[dict[str, list[TariffRecord]], list[str], list[str], list[str]]:
    """Match an edition's file positions with the stored versions of its date.

    Returns ``(same_dated, missing, conflicting, unlisted)``: per position its stored
    versions of that date, lowest first (the first is the edition's member, the rest are
    post-freeze successors); the positions with none; those whose member has other content
    than the file; and the stored positions of that date the file does not list.
    """

    effective = item.edition.effective_date
    same_dated: dict[str, list[TariffRecord]] = {}
    missing, conflicting = [], []
    for code, candidate in item.candidates.items():
        same_dated[code] = [v for v in versions_by_code.get(code, ()) if v.valid_from == effective]
        if not same_dated[code]:
            missing.append(code)
        elif not matches_prefill(candidate, same_dated[code][0]):
            conflicting.append(code)
    unlisted = sorted(
        code
        for code, versions in versions_by_code.items()
        if code not in item.candidates and any(v.valid_from == effective for v in versions)
    )
    return same_dated, missing, conflicting, unlisted


def _edition_fields(record: TariffRecord) -> tuple[Any, ...]:
    return tuple(getattr(record, name) for name in _EDITION_FIELDS)


def _history_problems(versions_by_code: dict[str, list[TariffRecord]]) -> list[str]:
    """Stored versions that rule out a safe placement.

    Undated rows cannot be ordered; versions out of effective-date order already serve
    the wrong edition; and versions of one date must agree on every billing and edition
    field, since a review or re-fill may only change non-billing fields.
    """

    undated = [
        f"{code} v{v.version}"
        for code, versions in versions_by_code.items()
        for v in versions
        if v.valid_from is None
    ]
    unordered = []
    changed = []
    for code, versions in versions_by_code.items():
        dated = [v for v in versions if v.valid_from is not None]
        if any(a.valid_from > b.valid_from for a, b in itertools.pairwise(dated)):
            steps = ", ".join(f"v{v.version} {v.valid_from}" for v in dated)
            unordered.append(f"{code}: {steps}")
        by_date: dict[date, set[tuple[Any, ...]]] = defaultdict(set)
        for v in dated:
            by_date[v.valid_from].add(_edition_fields(v))
        if any(len(fields) > 1 for fields in by_date.values()):
            changed.append(code)

    problems = []
    if changed:
        problems.append(
            f"{len(changed)} stored EAL position(s) have a later same-dated version that "
            f"changes a billing or edition field (e.g. {', '.join(changed[:5])}); within one "
            "edition only non-billing fields may change. Import into a database without "
            "such versions."
        )
    if undated:
        problems.append(
            f"{len(undated)} stored EAL version(s) for positions in this batch have no "
            f"valid_from (e.g. {', '.join(undated[:5])}); undated rows cannot be ordered "
            "against dated editions. Import into a database without undated EAL rows."
        )
    if unordered:
        problems.append(
            f"{len(unordered)} stored EAL position(s) have versions not in effective-date "
            f"order (e.g. {'; '.join(unordered[:3])}); as_of already serves the wrong "
            "edition there. Import into a database without out-of-order EAL versions."
        )
    return problems
