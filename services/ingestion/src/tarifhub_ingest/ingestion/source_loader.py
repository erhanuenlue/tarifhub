"""Discovery of source artifacts to ingest.

For the offline sample the artifacts ship in ``services/ingestion/sample-data/input``:
a tiny EAL-like XLSX (lab analyses, tax-point based, DE-only) and a tiny ePL-like
FHIR bundle (medications, price-based, multilingual). In production this is where a
scheduled loader would fetch from BAG / OAAT / MinIO.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarifhub_ingest.models.tariff_model import TariffSystem

# EAL (BAG Analysenliste) and SL (BAG ePL Spezialitätenliste) public source pages.
_EAL_SOURCE_URL = "https://www.bag.admin.ch/de/analysenliste-al"
_EPL_SOURCE_URL = "https://github.com/bag-epl/bag-epl-fhir"

_EAL_FILENAMES = ("eal_sample.xlsx", "eal_sample.csv", "bag_eal_sample.xlsx")
_EPL_FILENAMES = ("epl_sample.json", "bag_epl_sample.json")


@dataclass(frozen=True)
class SourceSpec:
    """A single source artifact and how to parse it."""

    system: TariffSystem
    kind: str  # "xlsx" | "fhir"
    path: Path
    source_url: str


def default_sample_dir() -> Path:
    """Resolve ``services/ingestion/sample-data/input`` relative to this package."""

    # .../services/ingestion/src/tarifhub_ingest/ingestion/source_loader.py
    service_root = Path(__file__).resolve().parents[3]
    return service_root / "sample-data" / "input"


def discover_samples(sample_dir: str | Path | None = None) -> list[SourceSpec]:
    """Return the available sample sources in a deterministic order (EAL, then ePL)."""

    base = Path(sample_dir) if sample_dir else default_sample_dir()
    specs: list[SourceSpec] = []

    eal = _first_existing(base, _EAL_FILENAMES)
    if eal:
        specs.append(
            SourceSpec(system=TariffSystem.EAL, kind="xlsx", path=eal, source_url=_EAL_SOURCE_URL)
        )

    epl = _first_existing(base, _EPL_FILENAMES)
    if epl:
        specs.append(
            SourceSpec(system=TariffSystem.SL, kind="fhir", path=epl, source_url=_EPL_SOURCE_URL)
        )

    return specs


def _first_existing(base: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = base / name
        if candidate.exists():
            return candidate
    return None
