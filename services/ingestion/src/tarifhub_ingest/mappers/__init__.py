"""Raw row -> canonical :class:`TariffRecord` mapping.

Rules-based by default and fully deterministic. ``ai_map`` is the single,
clearly-marked seam where a live Claude harmonizer may later be plugged in; it
falls back to the deterministic rules whenever no API key is configured and never
calls a live API during tests.
"""
