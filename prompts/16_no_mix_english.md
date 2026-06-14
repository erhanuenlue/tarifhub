# CAS thesis → ZERO German, no mix (run in a FRESH `claude` session at /effort ultracode)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan, then proceed. STOP only for: scope beyond this prompt, freeze-line contact, a green-contract/ratchet breach, or a destructive op.

Owner requirement (lecturer rule): the thesis must be **100% English — no German/English mix anywhere** in the PDF-bound docs. A previous pass left German terms in **parentheses** to protect `tools/cas_check.py` anchors (which grep the docs for German rubric strings). That was the wrong trade-off. This session removes ALL German from the thesis **and retargets `cas_check.py`'s anchors to English in lockstep**, so the docs are fully English and the floor stays **63/63**. Docs + `tools/cas_check.py` + `tools/build_pdf.py` only; no product code, no freeze-line files, no em-dashes. Branch `docs/no-mix-english`, then `/ship`; auto-merge on the green-contract.

## 1. Update `tools/cas_check.py` anchors German → English (keep IDs, weights, predicate LOGIC identical — translate ONLY the grep target strings)
Edit exactly these six predicates (plus any other German literal in `ELEMENTS()` grepped against a PDF-bound doc):
- `1.kern` (~line 102): `r"Kernfunktion"` → `r"[Cc]ore function"`.
- `3.kinutzen` (~line 113): `r"KI-Nutzen"` → `r"AI value"`.
- `8.quote` (~line 138): `r"gewählten Frameworks"` → `r"chosen framework"`.
- `15.phases` (~line 169): tuple `("Generierung", "Review", "Refactoring", "Recherche")` → `("Generation", "Review", "Refactoring", "Research")`.
- `15.erklaerung` (~line 171): `r"Eigenständigkeit"` → `r"Declaration of Authorship"`.
- `18.transfer` (~line 185): `r"Übertrag|künftig"` → `r"transfer|future"`.
Leave the German criterion NAMES in the `NAMES` dict alone (checker-internal display labels, never in the PDF). Do NOT hand-edit `tools/cas_baseline.json` — element IDs are unchanged, so the baseline still holds.

## 2. Remove ALL German from the PDF-bound docs (use the exact English the new anchors check for)
- `docs/method/ai-tools.md`: `Generierung (Generation)` → **Generation**, `Recherche (Research)` → **Research** (Review/Refactoring unchanged), heading `## Declaration of Authorship (Eigenständigkeit)` → **## Declaration of Authorship**.
- `docs/arc42/01-introduction-goals.md`: `Core functions (Kernfunktionen)` → **Core functions**, `AI value per core function (KI-Nutzen, Kernfunktion)` → **AI value per core function**, and any inline `(Kernfunktionen)`.
- `docs/arc42/08-crosscutting-concepts.md`: drop the `("gewählten Frameworks")` quote; keep **"Concepts of the chosen framework …"** in English.
- `docs/method/fazit.md`: `Transfer to future practice (Übertrag)` → **Transfer to future practice**; drop inline `(Übertrag)`; `Declaration of Authorship (Eigenständigkeitserklärung)` → **Declaration of Authorship**.
- `docs/criterion-map.md`: remove the German rubric quotes in the criterion descriptions (rows 8, 15, and any others) — keep the English description + evidence link.
- Then **sweep every PDF-bound doc** (`docs/arc42/*`, `docs/method/*`, `docs/index.md`, `docs/criterion-map.md`, the front-matter summary) for any remaining German (umlauts `äöüß`, German words) and translate it. The ONLY German allowed to remain is **proper nouns** (e.g. "Fernfachhochschule Schweiz", product/data names).

## 3. `tools/build_pdf.py`
- Declaration title `\chapter*{Declaration of Authorship (Eigenständigkeitserklärung)}` → **`\chapter*{Declaration of Authorship}`**.
- Confirm the front-matter summary renders English (no "Zusammenfassung (Deutsch)") and the cover/labels stay English ("Submitted to", "Advisor", English subtitle).

## 4. Verify (the no-mix gate) + rebuild + ship
- **Zero-German grep:** `grep -rniE 'ä|ö|ü|ß|Generierung|Recherche|gewählt|Eigenständ|Übertrag|künftig|Kernfunktion|KI-Nutzen|Zusammenfassung' docs/arc42 docs/method docs/criterion-map.md docs/index.md` returns **nothing but proper nouns** — list every remaining line and justify it.
- `python3 tools/cas_check.py` = **63/63** with the new English anchors (confirm the six IDs above still pass against the English docs). `mkdocs build -f docs/mkdocs.yml --strict` exit 0. Em-dash grep zero.
- Rebuild `python3 tools/build_pdf.py`; open it and confirm **no German anywhere** (cover, TOC, summary, every heading, the four phase headings, the declaration) except proper nouns, and the C5 diagram still renders.
- `/ship`; auto-merge on the green-contract.

## Done means
The thesis is 100% English (proper nouns aside); `cas_check.py` anchors are English and the floor is 63/63 against the English docs; CI green; merged; PDF rebuilt and visually confirmed German-free. Report the six cas_check anchor changes and the final zero-German grep result. Curate the journal entry.
