"""TarifIQ — the tarifhub intelligence service (Layer 2).

Deterministic combinability/cumulation rules, TARMED↔TARDOC cross-walk, and rule
validation, layered on top of the frozen tariff facts served by TarifCore (L1).

The freeze line still holds here: rule *evaluation* is deterministic and reads only
frozen rule/cross-walk tables. AI may *suggest* candidate rules pre-freeze (a single,
clearly marked, replaceable seam) for a human to review and freeze — it never evaluates
a rule and never computes or mutates a billing value.
"""

from __future__ import annotations

__version__ = "0.1.0"
