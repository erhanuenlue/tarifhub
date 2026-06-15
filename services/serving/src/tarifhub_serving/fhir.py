"""Hand-rolled minimal FHIR R4 facade over frozen tariff records (read-only).

Per ADR-008 we expose a FHIR R4 read adapter (ChargeItemDefinition / CodeSystem) over
the same frozen records the REST routes serve. These are *minimal, valid* R4 resources
hand-rolled as Pydantic v2 models — the ``fhir.resources`` dependency was rejected at
plan approval, so there are no new dependencies here.

Two doctrines hold throughout:

* **No AI, no value computation.** Every value emitted is an unaltered, frozen, versioned
  field read straight from a :class:`TariffRecord`. This module only reshapes; it never
  computes or alters a billing value. It imports only the canonical model from
  ``tarifhub_ingest`` (allowed by the serving boundary test).
* **No wall-clock branching.** The ``status`` of a resource is derived ONLY from record
  data, never from "today". For a ChargeItemDefinition the rule is: the record handed to
  the mapper is, by construction, the version selected by the caller (latest / as_of /
  explicit version); if it is the highest version of its key it is ``active``, otherwise
  it is ``retired`` (a superseded version). The caller passes ``is_latest`` so the rule
  stays a pure function of record data. A CodeSystem aggregates the latest version of
  each key and is therefore always ``active``.

FHIR decimals are JSON numbers. Billing values reach the wire value-preserved by going
out through :func:`float`: at our scales (``NUMERIC(12,4)``/``(12,2)``, <= 12 significant
digits) a Python ``Decimal`` round-trips exactly through ``float`` / IEEE-754 ``double``,
so ``Decimal(str(json_number)) == record.<field>``. The tests pin this round-trip.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from tarifhub_ingest.models.tariff_model import TariffRecord

# --- canonical URL space ------------------------------------------------------

_BASE = "https://tarifhub.example/fhir"
_CID_URL = f"{_BASE}/ChargeItemDefinition"
_CS_URL = f"{_BASE}/CodeSystem"
_RECORD_HASH_SD = f"{_BASE}/StructureDefinition/record-hash"
_SOURCE_URL_SD = f"{_BASE}/StructureDefinition/source-url"


def _fhir_id(*parts: str) -> str:
    """Build a FHIR-id-safe identifier from URL path parts.

    FHIR ``id`` is restricted to ``[A-Za-z0-9.\\-]{1,64}`` but, to keep ids stable and
    readable, we lower-case and replace every character outside ``[a-z0-9-]`` (notably the
    ``.`` in tariff codes such as ``AA.00.0010``) with a hyphen. The transform is
    documented in each route's OpenAPI description so consumers can reconstruct it.
    """

    raw = "-".join(parts).lower()
    return "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in raw)


# --- minimal R4 building blocks ----------------------------------------------


class FhirExtension(BaseModel):
    """A single R4 extension carrying record provenance as a ``valueString``."""

    url: str
    valueString: str


class FhirCoding(BaseModel):
    """One R4 Coding (system + code + display)."""

    system: str
    code: str
    display: str | None = None


class FhirCodeableConcept(BaseModel):
    """R4 CodeableConcept; ``text`` alone is valid when there is no coding."""

    coding: list[FhirCoding] | None = None
    text: str | None = None


class FhirMoney(BaseModel):
    """R4 Money: a JSON-number ``value`` plus an ISO-4217 ``currency`` code."""

    value: float
    currency: str


class FhirPeriod(BaseModel):
    """R4 Period; open ends (``None``) are omitted from the wire payload."""

    model_config = ConfigDict(extra="forbid")

    start: str | None = None
    end: str | None = None


class FhirPriceComponent(BaseModel):
    """One R4 ChargeItemDefinition.propertyGroup.priceComponent.

    ``base`` carries a CHF :class:`FhirMoney` ``amount``; ``informational`` carries the
    tax-point ``factor`` (a unitless multiplier) labelled via ``code.text``.
    """

    type: str
    code: FhirCodeableConcept | None = None
    amount: FhirMoney | None = None
    factor: float | None = None


class FhirPropertyGroup(BaseModel):
    """One R4 ChargeItemDefinition.propertyGroup."""

    priceComponent: list[FhirPriceComponent]


class ChargeItemDefinition(BaseModel):
    """Minimal valid R4 ChargeItemDefinition for one frozen tariff record."""

    resourceType: str = "ChargeItemDefinition"
    id: str
    url: str
    version: str
    status: str
    name: str
    title: str
    date: str
    extension: list[FhirExtension] | None = None
    code: FhirCodeableConcept
    effectivePeriod: FhirPeriod | None = None
    propertyGroup: list[FhirPropertyGroup] | None = None


class CodeSystemConceptDesignation(BaseModel):
    """An R4 CodeSystem.concept.designation (a non-canonical-language label)."""

    language: str
    value: str


class CodeSystemConcept(BaseModel):
    """One R4 CodeSystem.concept (code + German display + fr/it designations)."""

    code: str
    display: str
    designation: list[CodeSystemConceptDesignation] | None = None


class CodeSystem(BaseModel):
    """Minimal valid R4 CodeSystem for a tariff system's latest-version records."""

    resourceType: str = "CodeSystem"
    id: str
    url: str
    status: str = "active"
    content: str = "fragment"
    caseSensitive: bool = True
    publisher: str = "tarifhub"
    name: str
    title: str
    count: int = Field(..., ge=0)
    concept: list[CodeSystemConcept]


# --- mappers ------------------------------------------------------------------


def _provenance_extensions(record: TariffRecord) -> list[FhirExtension] | None:
    """Carry ``record_hash`` and ``source_url`` as plain valueString extensions.

    Honest provenance without inventing a bespoke profile: each is a single extension
    whose ``url`` names a StructureDefinition under the tarifhub canonical space. Absent
    fields are simply not emitted; an empty list collapses to ``None`` (omitted).
    """

    exts: list[FhirExtension] = []
    if record.record_hash:
        exts.append(FhirExtension(url=_RECORD_HASH_SD, valueString=record.record_hash))
    if record.source_url:
        exts.append(FhirExtension(url=_SOURCE_URL_SD, valueString=record.source_url))
    return exts or None


def _price_components(record: TariffRecord) -> list[FhirPriceComponent]:
    """Build the priceComponent list, omitting a component whose field is ``None``.

    ``price_chf`` -> a ``base`` component with a CHF Money amount. ``tax_points`` -> an
    ``informational`` component carrying the value as a ``factor``. Both go out through
    :func:`float` so the JSON number round-trips the stored ``Decimal`` exactly at our
    scales. An empty list (both fields ``None``) signals the caller to omit propertyGroup.
    """

    components: list[FhirPriceComponent] = []
    if record.price_chf is not None:
        components.append(
            FhirPriceComponent(
                type="base",
                amount=FhirMoney(value=float(record.price_chf), currency="CHF"),
            )
        )
    if record.tax_points is not None:
        components.append(
            FhirPriceComponent(
                type="informational",
                code=FhirCodeableConcept(text="tax_points"),
                factor=float(record.tax_points),
            )
        )
    return components


def to_charge_item_definition(
    system: str, code: str, record: TariffRecord, *, is_latest: bool
) -> ChargeItemDefinition:
    """Map ONE frozen :class:`TariffRecord` to a minimal valid R4 ChargeItemDefinition.

    ``is_latest`` (the highest version of the key exists and equals this record's version)
    drives the deterministic ``status`` rule: ``active`` when latest, ``retired`` when this
    is a superseded version. No wall-clock is consulted. ``system``/``code`` are the URL
    path parameters (used verbatim in the canonical ``url``); the resource's coding uses
    the record's own ``tariff_system``/``tariff_code`` so the payload stays self-describing.
    """

    rid = _fhir_id(system, code, str(record.version))
    status = "active" if is_latest else "retired"
    coding = FhirCoding(
        system=f"{_CS_URL}/{record.tariff_system.value}",
        code=record.tariff_code,
        display=record.designation.de,
    )
    period = None
    if record.valid_from is not None or record.valid_to is not None:
        period = FhirPeriod(
            start=record.valid_from.isoformat() if record.valid_from else None,
            end=record.valid_to.isoformat() if record.valid_to else None,
        )
    components = _price_components(record)
    property_group = [FhirPropertyGroup(priceComponent=components)] if components else None

    return ChargeItemDefinition(
        id=rid,
        url=f"{_CID_URL}/{system}/{code}",
        version=str(record.version),
        status=status,
        name=record.designation.de,
        title=record.designation.de,
        date=record.created_at.isoformat(),
        extension=_provenance_extensions(record),
        code=FhirCodeableConcept(coding=[coding]),
        effectivePeriod=period,
        propertyGroup=property_group,
    )


def to_code_system(system: str, records: list[TariffRecord], *, count: int) -> CodeSystem:
    """Map a window of a tariff system's latest-version records to ONE R4 CodeSystem.

    ``records`` is the (already paginated, ``tariff_code`` ascending) window the route
    fetched; ``count`` is the TOTAL number of ``(system, code)`` keys in the system. The
    payload is honestly ``content="fragment"`` because it carries a window, not necessarily
    the whole catalogue. ``status`` is always ``active`` (an aggregate of current records),
    derived from data, not the clock. fr/it designations are emitted only when non-None.
    """

    concepts: list[CodeSystemConcept] = []
    for record in records:
        designations: list[CodeSystemConceptDesignation] = []
        if record.designation.fr is not None:
            designations.append(
                CodeSystemConceptDesignation(language="fr", value=record.designation.fr)
            )
        if record.designation.it is not None:
            designations.append(
                CodeSystemConceptDesignation(language="it", value=record.designation.it)
            )
        concepts.append(
            CodeSystemConcept(
                code=record.tariff_code,
                display=record.designation.de,
                designation=designations or None,
            )
        )

    return CodeSystem(
        id=_fhir_id(system),
        url=f"{_CS_URL}/{system}",
        name=f"tarifhub-{system}",
        title=f"tarifhub {system} tariff codes",
        count=count,
        concept=concepts,
    )


# Re-export the round-trip helper so tests/callers can assert value preservation without
# re-deriving the scale rationale documented above.
def decimal_round_trips(value: Decimal) -> bool:
    """True when ``Decimal(str(float(value))) == value`` (value-preserving on the wire)."""

    return Decimal(str(float(value))) == value
