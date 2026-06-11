"""Adapter for the BAG ePL Spezialitätenliste (SL) — the real Swiss medication tariff.

Source: the BAG ePL FHIR R5 bulk export, one ``Bundle`` (``type=collection``,
profile ``ch-idmp-bundle``) per NDJSON line. Each bundle is an IDMP resource graph:
a ``MedicinalProductDefinition`` (multilingual name, ATC), one or more
``PackagedProductDefinition`` (one per SL package = the line item, keyed by GTIN),
and a PAIR of ``RegulatedAuthorization`` per package discriminated only by
``type.coding[].code`` — the FOPH "Reimbursement SL" one (``756000002003``) carries
all billing data on a ``reimbursementSL`` extension.

``parse`` is a pure function of the file (no AI, no network): it streams the NDJSON
and emits one canonical-keyed ``dict`` per GTIN-keyable reimbursed package, plus a
``{"_parse_failure": True}`` marker (no record content) for every reimbursed package
that cannot be keyed by GTIN — a parsing failure must never produce a frozen record.
``fetch`` (stdlib only, used by the scale-run driver, never by tests) resolves the
public manifest, downloads the artifact and writes a ``.sha256`` sidecar idempotently.

``valid_from`` / ``source_version`` are derived purely from the FILENAME convention
``foph-sl-export-YYYYMMDD.ndjson`` — a deterministic function of the input path, so
re-ingesting the same file always yields the same frozen records.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

ADAPTER_VERSION = "bag-epl/0.1.0"

_LOG = logging.getLogger(__name__)

# Hostile-input guards: the real export is ~93 MB / 6 763 lines. Refuse anything
# wildly outside that envelope rather than letting a malformed file exhaust memory.
_MAX_BYTES = 200 * 1024 * 1024  # 200 MB
_MAX_LINES = 20_000
_MAX_LINE_BYTES = 4 * 1024 * 1024  # 4 MB per bundle line

# Network guard for fetch(): https only, host EXACTLY the ePL service (SSRF / file://).
_FETCH_TIMEOUT_S = 30
_FETCH_MAX_BYTES = 200 * 1024 * 1024
_CHUNK = 64 * 1024
_ALLOWED_SCHEME = "https"
_ALLOWED_HOST = "epl.bag.admin.ch"
_MANIFEST_URL = "https://epl.bag.admin.ch/api/sl/public/resources/current"
_STATIC_BASE = "https://epl.bag.admin.ch/static/"

# FHIR coding systems / codes we key on (NEVER on id/display/narrative/position).
_ATC_SYSTEM = "http://www.whocc.no/atc"
_GTIN_SYSTEM = "urn:oid:2.51.1.1"
_AUTHNO_SYSTEM = "http://fhir.ch/ig/ch-epl/sid/authno"
_AUTH_TYPE_REIMBURSEMENT = "756000002003"  # FOPH "Reimbursement SL" authorisation
_AUTH_TYPE_MARKETING = "756000002001"  # Swissmedic marketing authorisation
_PRICE_RETAIL = "756002005001"  # Publikumspreis -> price_chf
_PRICE_EX_FACTORY = "756002005002"  # Ex-factory -> metadata

# Extension urls — matched EXACTLY at each nesting level (both reimbursementSL and the
# limitation extension carry a `status` child; never flatten by name globally).
_EXT_REIMBURSEMENT_SL = "http://fhir.ch/ig/ch-epl/StructureDefinition/reimbursementSL"
_EXT_PRODUCT_PRICE = "http://fhir.ch/ig/ch-epl/StructureDefinition/productPrice"

# A 2100-12-31 end date is the SL "open-ended" sentinel (treated as absent / None).
_OPEN_ENDED_SENTINEL = "2100-12-31"

# BCP-47 language tag (e.g. "de-CH") -> canonical designation key.
_LANG_TO_KEY = {"de": "designation_de", "fr": "designation_fr", "it": "designation_it"}

# foph-sl-export-YYYYMMDD.ndjson  ->  the publication date.
_FILENAME_DATE_RE = re.compile(r"foph-sl-export-(\d{4})(\d{2})(\d{2})", re.IGNORECASE)


def parse(path: str | Path) -> list[dict[str, Any]]:
    """Parse a BAG ePL FHIR R5 NDJSON export into canonical-keyed row dicts.

    Streams the file line by line (never reads the whole export into one string).
    Emits one dict per GTIN-keyable reimbursed package (the SL line item). A
    reimbursed package that cannot be keyed by GTIN yields a ``_parse_failure``
    marker instead of a record, so unkeyable bundles never reach map/freeze while
    still being counted deterministically by the pipeline. Prices are parsed with
    ``parse_float=Decimal`` so no billing value ever transits a binary float.

    Raises ``ValueError`` on a structurally undecodable (invalid JSON) line, a
    duplicate GTIN across the export (the frozen join key), or any hostile-input
    guard breach.
    """

    path = Path(path)
    _guard_file_size(path)

    valid_from = _date_from_filename(path.name)
    source_version = _source_version_from_filename(path.name)

    rows: list[dict[str, Any]] = []
    seen_gtins: set[str] = set()

    with open(path, "rb") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if line_no > _MAX_LINES:
                raise ValueError(
                    f"BAG ePL export exceeds the {_MAX_LINES} line limit; refusing to parse"
                )
            if len(raw_line) > _MAX_LINE_BYTES:
                raise ValueError(
                    f"BAG ePL export line {line_no} is {len(raw_line)} bytes, over the "
                    f"{_MAX_LINE_BYTES} per-line byte limit; refusing to parse"
                )
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                bundle = json.loads(stripped, parse_float=Decimal)
            except json.JSONDecodeError as exc:
                # File-level hard fail: a parsing failure must never silently drop data.
                raise ValueError(f"BAG ePL export line {line_no} is not valid JSON: {exc}") from exc

            _emit_bundle_rows(
                bundle,
                valid_from=valid_from,
                source_version=source_version,
                seen_gtins=seen_gtins,
                rows=rows,
            )

    return rows


def fetch(dest_dir: str | Path) -> Path:
    """Resolve the public ePL manifest, download the current export, write a sidecar.

    Idempotent: if the resolved destination already exists and its hash matches the
    ``.sha256`` sidecar, the download is skipped. NOT used by the test suite (no
    network in tests) — this is the scale-run driver's entry point.
    """

    manifest_url = _MANIFEST_URL
    _validate_fetch_url(manifest_url)
    manifest = json.loads(_download_bytes(manifest_url, _FETCH_MAX_BYTES))
    file_url_rel = (manifest.get("fhir") or {}).get("fileUrl")
    if not file_url_rel:
        raise ValueError("ePL manifest has no .fhir.fileUrl")
    file_url = urljoin(_STATIC_BASE, file_url_rel)
    _validate_fetch_url(file_url)

    dest_dir = Path(dest_dir)
    dest = dest_dir / Path(urlsplit(file_url).path).name
    sidecar = dest.with_name(dest.name + ".sha256")

    if dest.exists() and sidecar.exists():
        recorded = sidecar.read_text(encoding="utf-8").split()[0].strip()
        if recorded and recorded == _sha256_file(dest):
            return dest  # already present and intact

    dest_dir.mkdir(parents=True, exist_ok=True)
    digest = _stream_to_file(file_url, dest, _FETCH_MAX_BYTES)
    sidecar.write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
    return dest


# --------------------------------------------------------------------------- #
# Bundle -> rows
# --------------------------------------------------------------------------- #


def _emit_bundle_rows(
    bundle: dict[str, Any],
    *,
    valid_from: date | None,
    source_version: str | None,
    seen_gtins: set[str],
    rows: list[dict[str, Any]],
) -> None:
    """Emit one row per GTIN-keyable reimbursed package; a marker for unkeyable ones."""

    entries = bundle.get("entry") or []
    mpd = _first_of_type(entries, "MedicinalProductDefinition") or {}
    designations = _designations(mpd)
    category = _atc_code(mpd)
    has_limitation, limitation_count = _limitation_info(entries)

    packages = _packages_by_id(entries)  # ppd id -> {gtin, unit}
    marketing_authno = _marketing_authno_by_package(entries)  # ppd id -> authno

    for ra in entries:
        resource = ra.get("resource") or {}
        if resource.get("resourceType") != "RegulatedAuthorization":
            continue
        if _authorisation_type(resource) != _AUTH_TYPE_REIMBURSEMENT:
            continue

        ppd_id = _subject_ppd_id(resource)
        package = packages.get(ppd_id) if ppd_id else None
        gtin = package.get("gtin") if package else None
        if not gtin:
            # Unkeyable reimbursed package: fail closed (no record, counted upstream).
            _LOG.warning(
                "BAG ePL: reimbursed package without resolvable GTIN "
                "(ppd id %r); emitting parse_failure, no record",
                ppd_id,
            )
            rows.append({"_parse_failure": True})
            continue

        if gtin in seen_gtins:
            raise ValueError(
                f"BAG ePL export repeats GTIN {gtin!r}; GTINs must be unique (frozen join key)"
            )
        seen_gtins.add(gtin)

        prices = _reimbursement_prices(resource)
        sl_fields = _reimbursement_fields(resource)
        retail = prices.get(_PRICE_RETAIL)
        ex_factory = prices.get(_PRICE_EX_FACTORY)

        metadata = _build_metadata(
            ex_factory=ex_factory,
            sl_fields=sl_fields,
            swissmedic_authno=marketing_authno.get(ppd_id),
            has_limitation=has_limitation,
            limitation_count=limitation_count,
        )

        rows.append(
            {
                "tariff_code": gtin,
                "designation_de": designations.get("designation_de"),
                "designation_fr": designations.get("designation_fr"),
                "designation_it": designations.get("designation_it"),
                "category": category,
                "price_chf": retail,  # RETAIL price as Decimal (or None)
                "tax_points": None,  # SL is money-only — verified zero tax points
                "unit": package.get("unit"),
                "valid_from": valid_from,
                "source_version": source_version,
                "metadata": metadata,
            }
        )


def _build_metadata(
    *,
    ex_factory: Decimal | None,
    sl_fields: dict[str, Any],
    swissmedic_authno: str | None,
    has_limitation: bool,
    limitation_count: int,
) -> dict[str, Any]:
    """Assemble the JSON-native SL metadata extras (no Decimal objects).

    Every value here must survive ``json.dumps`` — prices become strings, dates stay
    ISO strings, counts/percentages stay ints, flags stay bools — because metadata
    participates in the record_hash and must be byte-stable.
    """

    metadata: dict[str, Any] = {
        "has_limitation": has_limitation,
        "limitation_count": limitation_count,
    }
    if ex_factory is not None:
        metadata["ex_factory_chf"] = _decimal_str(ex_factory)
    if swissmedic_authno is not None:
        metadata["swissmedic_authno"] = swissmedic_authno
    if sl_fields.get("dossier_number") is not None:
        metadata["dossier_number"] = sl_fields["dossier_number"]
    if sl_fields.get("cost_share_pct") is not None:
        metadata["cost_share_pct"] = sl_fields["cost_share_pct"]
    if sl_fields.get("first_listing_date") is not None:
        metadata["first_listing_date"] = sl_fields["first_listing_date"]
    if sl_fields.get("price_change_date") is not None:
        metadata["price_change_date"] = sl_fields["price_change_date"]
    if sl_fields.get("price_change_type") is not None:
        metadata["price_change_type"] = sl_fields["price_change_type"]
    return metadata


# --------------------------------------------------------------------------- #
# MedicinalProductDefinition helpers
# --------------------------------------------------------------------------- #


def _designations(mpd: dict[str, Any]) -> dict[str, str | None]:
    """Extract de/fr/it product names keyed by ``name[].usage[].language``.

    Discriminates the sliced ``name`` array by its declared language (content), never
    by position. A name with no usable language tag is skipped.
    """

    out: dict[str, str | None] = {}
    for name in mpd.get("name") or []:
        product_name = _as_text(name.get("productName"))
        if not product_name:
            continue
        for usage in name.get("usage") or []:
            for coding in (usage.get("language") or {}).get("coding") or []:
                code = _as_text(coding.get("code"))
                if not code:
                    continue
                key = _LANG_TO_KEY.get(code.split("-")[0].lower())
                if key and key not in out:
                    out[key] = product_name
    return out


def _atc_code(mpd: dict[str, Any]) -> str | None:
    """The ATC classification code (system whocc.no/atc), or None (the category gap)."""

    for classification in mpd.get("classification") or []:
        for coding in classification.get("coding") or []:
            if coding.get("system") == _ATC_SYSTEM:
                code = _as_text(coding.get("code"))
                if code:
                    return code
    return None


# --------------------------------------------------------------------------- #
# PackagedProductDefinition helpers
# --------------------------------------------------------------------------- #


def _packages_by_id(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map ``PackagedProductDefinition.id`` -> ``{gtin, unit}``.

    GTIN is the ``packaging.identifier`` with system ``urn:oid:2.51.1.1``; a PPD with
    no ``packaging`` (the real unkeyable case) maps to ``gtin=None``.
    """

    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        resource = entry.get("resource") or {}
        if resource.get("resourceType") != "PackagedProductDefinition":
            continue
        ppd_id = _as_text(resource.get("id"))
        if not ppd_id:
            continue
        out[ppd_id] = {
            "gtin": _gtin(resource),
            "unit": _pack_size(resource),
        }
    return out


def _gtin(ppd: dict[str, Any]) -> str | None:
    for identifier in (ppd.get("packaging") or {}).get("identifier") or []:
        if identifier.get("system") == _GTIN_SYSTEM:
            return _as_text(identifier.get("value"))
    return None


def _pack_size(ppd: dict[str, Any]) -> str | None:
    """Pack size string (e.g. '60 Stk') from ``containedItemQuantity[].unit``."""

    for quantity in ppd.get("containedItemQuantity") or []:
        unit = _as_text(quantity.get("unit"))
        if unit:
            return unit
    return None


# --------------------------------------------------------------------------- #
# RegulatedAuthorization helpers
# --------------------------------------------------------------------------- #


def _authorisation_type(ra: dict[str, Any]) -> str | None:
    for coding in (ra.get("type") or {}).get("coding") or []:
        code = _as_text(coding.get("code"))
        if code:
            return code
    return None


def _subject_ppd_id(ra: dict[str, Any]) -> str | None:
    """Resolve the package id from ``subject[].reference``.

    References look like ``CHIDMPPackagedProductDefinition/<id>`` (the bundle's
    fullUrls drop the CHIDMP prefix), so we key on the trailing ``<id>`` after the
    last '/' — None-safe for the R5 CodeableReference-with-only-extension case.
    """

    for subject in ra.get("subject") or []:
        reference = _as_text(subject.get("reference"))
        if reference:
            return reference.rsplit("/", 1)[-1]
    return None


def _marketing_authno_by_package(entries: list[dict[str, Any]]) -> dict[str, str]:
    """Map package id -> Swissmedic authno from the package-level marketing RA.

    The marketing authorisation (``756000002001``) that references a PACKAGE carries
    the package's Swissmedic authno (``identifier`` system ``.../authno``). The one
    referencing the product carries the product authno — we want the package's.
    """

    out: dict[str, str] = {}
    for entry in entries:
        resource = entry.get("resource") or {}
        if resource.get("resourceType") != "RegulatedAuthorization":
            continue
        if _authorisation_type(resource) != _AUTH_TYPE_MARKETING:
            continue
        ppd_id = _subject_ppd_id(resource)
        if not ppd_id:
            continue
        for identifier in resource.get("identifier") or []:
            if identifier.get("system") == _AUTHNO_SYSTEM:
                value = _as_text(identifier.get("value"))
                if value:
                    out[ppd_id] = value
                    break
    return out


def _reimbursement_extension(ra: dict[str, Any]) -> dict[str, Any] | None:
    for ext in ra.get("extension") or []:
        if ext.get("url") == _EXT_REIMBURSEMENT_SL:
            return ext
    return None


def _reimbursement_prices(ra: dict[str, Any]) -> dict[str, Decimal]:
    """Map price-type code -> Money value (Decimal) from the SL ``productPrice``\\ s.

    Each ``productPrice`` is a sub-extension whose own children (``type`` /
    ``value`` / ``changeType`` / ``changeDate``) use RELATIVE url strings; we match
    them exactly at this nesting level. ``value`` is a ``valueMoney`` already parsed
    as Decimal upstream — never coerced through float.
    """

    sl_ext = _reimbursement_extension(ra)
    if not sl_ext:
        return {}
    prices: dict[str, Decimal] = {}
    for sub in sl_ext.get("extension") or []:
        if sub.get("url") != _EXT_PRODUCT_PRICE:
            continue
        price_type = None
        money_value: Decimal | None = None
        for child in sub.get("extension") or []:
            url = child.get("url")
            if url == "type":
                price_type = _codeable_code(child.get("valueCodeableConcept"))
            elif url == "value":
                money_value = _money_value(child.get("valueMoney"))
        if price_type is not None and money_value is not None:
            prices.setdefault(price_type, money_value)
    return prices


def _reimbursement_fields(ra: dict[str, Any]) -> dict[str, Any]:
    """Extract scalar SL fields from the ``reimbursementSL`` extension.

    Matches each sub-extension by its RELATIVE url string exactly (so the
    reimbursementSL ``status`` is never confused with a limitation ``status``). Also
    pulls the change date/type off the RETAIL ``productPrice`` for metadata.
    """

    sl_ext = _reimbursement_extension(ra)
    fields: dict[str, Any] = {}
    if not sl_ext:
        return fields

    for sub in sl_ext.get("extension") or []:
        url = sub.get("url")
        if url == "FOPHDossierNumber":
            ident = sub.get("valueIdentifier") or {}
            fields["dossier_number"] = _as_text(ident.get("value"))
        elif url == "costShare":
            value = sub.get("valueInteger")
            if isinstance(value, int) and not isinstance(value, bool):
                fields["cost_share_pct"] = value
        elif url == "firstListingDate":
            fields["first_listing_date"] = _date_or_none(sub.get("valueDate"))
        elif url == _EXT_PRODUCT_PRICE:
            if _codeable_code_in_price(sub) == _PRICE_RETAIL:
                fields.setdefault(
                    "price_change_date", _date_or_none(_price_child_date(sub, "changeDate"))
                )
                fields.setdefault("price_change_type", _price_change_type(sub))

    return fields


def _codeable_code_in_price(price_ext: dict[str, Any]) -> str | None:
    for child in price_ext.get("extension") or []:
        if child.get("url") == "type":
            return _codeable_code(child.get("valueCodeableConcept"))
    return None


def _price_child_date(price_ext: dict[str, Any], url: str) -> Any:
    for child in price_ext.get("extension") or []:
        if child.get("url") == url:
            return child.get("valueDate")
    return None


def _price_change_type(price_ext: dict[str, Any]) -> str | None:
    for child in price_ext.get("extension") or []:
        if child.get("url") == "changeType":
            return _codeable_code(child.get("valueCodeableConcept"))
    return None


# --------------------------------------------------------------------------- #
# ClinicalUseDefinition (limitations) helpers
# --------------------------------------------------------------------------- #


def _limitation_info(entries: list[dict[str, Any]]) -> tuple[bool, int]:
    """(has_limitation, count) over ``ClinicalUseDefinition`` entries in the bundle."""

    count = sum(
        1
        for entry in entries
        if (entry.get("resource") or {}).get("resourceType") == "ClinicalUseDefinition"
    )
    return count > 0, count


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #


def _first_of_type(entries: list[dict[str, Any]], resource_type: str) -> dict[str, Any] | None:
    for entry in entries:
        resource = entry.get("resource") or {}
        if resource.get("resourceType") == resource_type:
            return resource
    return None


def _codeable_code(codeable: Any) -> str | None:
    if not isinstance(codeable, dict):
        return None
    for coding in codeable.get("coding") or []:
        code = _as_text(coding.get("code"))
        if code:
            return code
    return None


def _money_value(money: Any) -> Decimal | None:
    if not isinstance(money, dict):
        return None
    value = money.get("value")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = _as_text(value)
    if text is None:
        return None
    try:
        return Decimal(text)
    except (ArithmeticError, ValueError):
        return None


def _date_or_none(value: Any) -> str | None:
    """Return an ISO date string, treating the open-ended sentinel as None."""

    text = _as_text(value)
    if text is None or text == _OPEN_ENDED_SENTINEL:
        return None
    return text


def _decimal_str(value: Decimal) -> str:
    """Render a Decimal as a JSON-native, normalised string ('191.90' -> '191.9')."""

    return format(value.normalize(), "f")


def _date_from_filename(name: str) -> date | None:
    match = _FILENAME_DATE_RE.search(name)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _source_version_from_filename(name: str) -> str | None:
    parsed = _date_from_filename(name)
    return f"BAG SL {parsed.isoformat()}" if parsed else None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _guard_file_size(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"BAG ePL source not found: {path}")
    size = path.stat().st_size
    if size > _MAX_BYTES:
        raise ValueError(
            f"BAG ePL source is {size} bytes, over the {_MAX_BYTES} limit; refusing to parse"
        )


def _validate_fetch_url(url: str) -> None:
    """Reject anything but https on the EXACT ePL host (SSRF / file:// guard)."""

    parts = urlsplit(url)
    if parts.scheme != _ALLOWED_SCHEME:
        raise ValueError(
            f"fetch URL scheme must be {_ALLOWED_SCHEME!r}, got {parts.scheme!r}: {url}"
        )
    host = (parts.hostname or "").lower()
    if host != _ALLOWED_HOST:
        raise ValueError(f"fetch URL host must be exactly {_ALLOWED_HOST!r}, got {host!r}: {url}")


def _download_bytes(url: str, max_bytes: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "tarifhub-ingest"})
    chunks: list[bytes] = []
    total = 0
    with urllib.request.urlopen(  # noqa: S310 — host/scheme pinned by _validate_fetch_url
        request, timeout=_FETCH_TIMEOUT_S
    ) as response:
        while True:
            chunk = response.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"download exceeded {max_bytes} bytes; aborted")
            chunks.append(chunk)
    return b"".join(chunks)


def _stream_to_file(url: str, dest: Path, max_bytes: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "tarifhub-ingest"})
    digest = hashlib.sha256()
    total = 0
    with (
        urllib.request.urlopen(  # noqa: S310 — host/scheme pinned by _validate_fetch_url
            request, timeout=_FETCH_TIMEOUT_S
        ) as response,
        open(dest, "wb") as handle,
    ):
        while True:
            chunk = response.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                handle.close()
                dest.unlink(missing_ok=True)
                raise ValueError(f"download exceeded {max_bytes} bytes; aborted")
            handle.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()
