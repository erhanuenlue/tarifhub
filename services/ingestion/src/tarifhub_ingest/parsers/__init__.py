"""Source-format parsers.

Each parser turns a raw source artifact into a list of flat ``dict`` rows using a
common key vocabulary (``tariff_code``, ``designation_de`` …). Parsers never map
to the canonical model and never call an LLM.
"""
