"""Source-specific ingestion adapters.

An adapter turns one external publication format into a list of canonical-keyed
``dict`` rows that the deterministic mapper (:mod:`tarifhub_ingest.mappers`) can
consume. Adapters do NO AI and (in ``parse``) NO network — they are pure functions
of their input file, so the pipeline stays deterministic and offline-testable.
"""
