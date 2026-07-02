"""Read-only access to FROZEN tariff facts from the L1 TarifCore serving API.

TarifIQ never owns tariff values; it confirms that the codes a rule or cross-walk talks
about exist as frozen records, and can fetch their designations. Two implementations
behind one tiny protocol:

* :class:`ServingFrozenClient` — httpx client against ``SERVING_BASE_URL`` (production).
  A custom transport can be injected so tests exercise it without touching the network.
* :class:`OfflineFrozenStore` — an in-memory, bundled snapshot used by the test suite and
  offline dev (the default), so the whole service runs with zero external dependencies.

No LLM client is imported here: this is the deterministic value-adjacent path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

import httpx

from tarifiq.config import Settings


@dataclass(frozen=True)
class FrozenTariff:
    """A frozen tariff record as TarifIQ needs it (values are read-only, never computed)."""

    tariff_code: str
    tariff_system: str
    designation_de: str
    tax_points: Optional[str] = None
    price_chf: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    record_hash: Optional[str] = None


class FrozenStore(Protocol):
    """The minimal read surface TarifIQ depends on."""

    def get(self, system: str, code: str) -> Optional[FrozenTariff]:
        """Return the frozen record for ``(system, code)``, or ``None``."""
        ...

    def exists(self, system: str, code: str) -> bool:
        """True iff a frozen record exists for ``(system, code)``."""
        ...


class OfflineFrozenStore:
    """In-memory frozen store backed by a bundled snapshot (offline default)."""

    def __init__(self, records: Iterable[FrozenTariff]):
        self._by_key: dict[tuple[str, str], FrozenTariff] = {
            (r.tariff_system, r.tariff_code): r for r in records
        }

    def get(self, system: str, code: str) -> Optional[FrozenTariff]:
        """Return the bundled snapshot's record for ``(system, code)``, or ``None``."""

        return self._by_key.get((system, code))

    def exists(self, system: str, code: str) -> bool:
        """True iff the bundled snapshot carries a record for ``(system, code)``."""

        return (system, code) in self._by_key


# A small, frozen snapshot mirroring records the L1 serving API would return. Enough to
# back the bundled rule set and cross-walk so the service is coherent fully offline.
_BUNDLED_RECORDS: tuple[FrozenTariff, ...] = (
    FrozenTariff("AA.00.0010", "TARDOC", "Grundkonsultation, erste 5 Min.", "9.57", None, "2026-01-01", None, "f0010"),
    FrozenTariff("AA.00.0020", "TARDOC", "Konsultationszuschlag Kind < 6 J.", "4.10", None, "2026-01-01", None, "f0020"),
    FrozenTariff("AA.00.0030", "TARDOC", "Telefonkonsultation, erste 5 Min.", "8.12", None, "2026-01-01", None, "f0030"),
    FrozenTariff("AA.00.0050", "TARDOC", "Konsultation, jede weiteren 5 Min.", "8.19", None, "2026-01-01", None, "f0050"),
    FrozenTariff("AA.10.0010", "TARDOC", "Kleiner rheumatologischer Status", "12.44", None, "2026-01-01", None, "f1010"),
)


def bundled_offline_store() -> OfflineFrozenStore:
    """Return the default offline store seeded with the bundled frozen snapshot."""

    return OfflineFrozenStore(_BUNDLED_RECORDS)


class ServingFrozenClient:
    """httpx client that reads single frozen records from the serving API.

    ``GET /api/v1/tariffs/{system}/{code}`` returns a frozen record (camelCase JSON) or
    404. A custom ``transport`` lets tests drive it with ``httpx.MockTransport`` offline.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url, timeout=self._timeout, transport=self._transport
        )

    def get(self, system: str, code: str) -> Optional[FrozenTariff]:
        """Read one frozen record from the serving API; a 404 maps to ``None``."""

        with self._client() as client:
            resp = client.get(f"/api/v1/tariffs/{system}/{code}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return _from_serving_json(resp.json())

    def exists(self, system: str, code: str) -> bool:
        """True iff the serving API has a frozen record for ``(system, code)``."""

        return self.get(system, code) is not None


def _from_serving_json(data: dict) -> FrozenTariff:
    """Map a serving record (camelCase, snake_case fallback) onto :class:`FrozenTariff`."""

    def pick(*keys: str) -> Optional[str]:
        for key in keys:
            value = data.get(key)
            if value is not None:
                return str(value)
        return None

    return FrozenTariff(
        tariff_code=pick("tariffCode", "tariff_code") or "",
        tariff_system=pick("tariffSystem", "tariff_system") or "",
        designation_de=pick("designationDe", "designation_de") or "",
        tax_points=pick("taxPoints", "tax_points"),
        price_chf=pick("priceChf", "price_chf"),
        valid_from=pick("validFrom", "valid_from"),
        valid_to=pick("validTo", "valid_to"),
        record_hash=pick("recordHash", "record_hash"),
    )


def get_frozen_store(settings: Settings) -> FrozenStore:
    """Choose the frozen store: bundled offline stub (default) or the live serving client."""

    if settings.offline or not settings.serving_base_url:
        return bundled_offline_store()
    return ServingFrozenClient(settings.serving_base_url, timeout=settings.request_timeout)
