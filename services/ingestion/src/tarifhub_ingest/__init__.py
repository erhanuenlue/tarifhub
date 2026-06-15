"""tarifhub ingestion service.

AI-assisted harmonization of Swiss ambulatory tariff data. Everything in this
package runs *before* the freeze line: load -> parse -> map -> validate -> score
-> flag -> freeze -> store -> audit. After a record is frozen it is an immutable,
versioned, hashed fact that the (separate) serving service returns deterministically.
"""

__version__ = "0.1.0"
