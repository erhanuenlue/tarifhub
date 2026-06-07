"""Persistence adapters: DB connection + tariff repository.

SQLite by default (offline dev/test), Postgres-ready via the same interface. This
package is on the value-serving path and therefore never imports an LLM client.
"""
