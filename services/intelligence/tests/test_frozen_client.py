"""Frozen-store selection and the offline read surface (fully offline, no network).

Covers the bundled ``OfflineFrozenStore.get`` read path (the existing suite exercised
only ``exists``) and ``get_frozen_store``'s three-way choice: bundled store when offline,
bundled store when a base URL is missing even though ``offline=False``, and the live
``ServingFrozenClient`` only when online with a configured base URL. Constructing the
serving client makes no request, so this stays hermetic.
"""

from __future__ import annotations

from tarifiq.config import Settings
from tarifiq.store.frozen_client import (
    FrozenTariff,
    OfflineFrozenStore,
    ServingFrozenClient,
    bundled_offline_store,
    get_frozen_store,
)


def test_offline_store_get_returns_bundled_record_and_none_for_miss():
    """``OfflineFrozenStore.get`` returns the bundled record, or ``None`` for a miss."""

    store = bundled_offline_store()

    record = store.get("TARDOC", "AA.00.0010")
    assert isinstance(record, FrozenTariff)
    assert record.tariff_code == "AA.00.0010"
    assert record.designation_de == "Grundkonsultation, erste 5 Min."
    assert record.tax_points == "9.57"

    assert store.get("TARDOC", "ZZ.99.9999") is None


def test_get_frozen_store_offline_returns_bundled_store():
    """With ``offline=True`` the bundled in-memory store is used (no serving client)."""

    store = get_frozen_store(Settings(offline=True, serving_base_url="http://serving.test"))
    assert isinstance(store, OfflineFrozenStore)


def test_get_frozen_store_online_without_base_url_falls_back_to_bundled():
    """``offline=False`` but an empty base URL still yields the bundled store (fail-safe)."""

    store = get_frozen_store(Settings(offline=False, serving_base_url=""))
    assert isinstance(store, OfflineFrozenStore)


def test_get_frozen_store_online_with_base_url_returns_serving_client():
    """Only when online AND a base URL is set do we get the live serving client."""

    store = get_frozen_store(Settings(offline=False, serving_base_url="http://serving.test"))
    assert isinstance(store, ServingFrozenClient)
