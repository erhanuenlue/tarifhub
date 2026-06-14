# CAS thesis → fully English (run in a FRESH `claude` session at /effort ultracode)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan, then proceed. STOP only for: scope beyond this prompt, freeze-line contact, a green-contract/ratchet breach, or a destructive op.

Owner decision: the CAS thesis must read as a **fully English** document — translate ALL German prose, headings, labels, the abstract, the cover subtitle, and the formal pages to English. **One hard exception (step 1): the specific German strings `tools/cas_check.py` anchors on must stay verbatim** — they are the official German rubric's own terms, and a thesis correctly quotes its grading rubric in the original. Documentation + the PDF build template only; no product code, no freeze-line files, NO edits to `tools/cas_check.py` or `tools/cas_baseline.json`, no em-dashes. Branch `docs/fully-english`, then `/ship`; auto-merge on the green-contract.

## 1. FIRST: find and protect the cas_check anchors (before translating anything)
`grep` `tools/cas_check.py` (`ELEMENTS()`) for every German literal it checks. Known anchors that MUST remain verbatim in the docs (gloss them in English in parentheses where it helps, but keep the German string present so the predicate matches):
- Criterion-15 phase taxonomy: **Generierung, Review, Refactoring, Recherche** (15.phases needs all four).
- Criterion-8 verbatim rubric quote: **"gewählten Frameworks"** (8.quote).
- Criterion-15: **Eigenständigkeit** (15.erklaerung).
- Criterion-18 transfer: **Übertrag** or **künftig** (18.transfer).
- Any other German literal you find in `ELEMENTS()` — treat identically.
Everything else German becomes English. **`cas_check` must read 63/63 at the end.**

## 2. Translate the body docs to English
Across `docs/arc42/*.md` and `docs/method/*.md`, translate every German heading and inline German label to clean English: `Problemstellung`→Problem statement, `Fehlerbehandlung`→Error handling, `Tests der KI-Anteile`→Tests of the AI components, `Kernfunktionen`→Core functions, `KI-Nutzen je Kernfunktion`→AI value per core function, Vision labels `Zielgruppe/Bedürfnis/Abgrenzung`→Target group/Need/Scope, `Kernaussage (Deutsch)`→Key message, `Erklärung der Eigenständigkeit`→Declaration of Authorship (keep the word "Eigenständigkeit" per step 1, e.g. "Declaration of Authorship (Eigenständigkeit)"). For the criterion-15 phase headings keep the German rubric term + an English gloss, e.g. "Generierung (Generation)". Preserve all evidence, commit refs, and meaning.

## 3. Translate the abstract to English
Translate `docs/zusammenfassung-de.md` (the "Zusammenfassung (Deutsch)") into English and retitle it "Summary" (or "Abstract"); update the build so the front-matter abstract renders in English (adjust the section title / file reference the build uses).

## 4. Make the PDF template English (`tools/build_pdf.py` + the build preamble only — NOT the official `ffhsthesis.cls`)
- Switch the document language to English so auto labels render English: `Inhaltsverzeichnis`→Contents, `Anhang`→Appendix, list-of-figures, etc. (set babel/polyglossia to English; also fixes hyphenation).
- Cover subtitle: `KI-gestützte Harmonisierung über einer deterministischen Freeze-Line` → "AI-assisted harmonisation over a deterministic freeze line".
- Cover institutional labels the class emits: `Eingereicht bei`→Submitted to, `Referent`→Advisor, `von`→by, `Projektarbeit`→Project thesis, `Schweiz, 2026`→Switzerland, 2026. Do this by `\renewcommand`-ing the label macros in the build preamble — **do NOT edit the official `ffhsthesis.cls`**. If a label is hardcoded in the class and cannot be overridden from the preamble, leave it and note it in your report rather than hacking the template.
- Formal pages: `Selbstständigkeitserklärung`→Declaration of Authorship (keep the German term once for the `Eigenständigkeit` anchor), `Hilfsmittelverzeichnis`→List of Aids/Resources — titles and body.

## 5. Verify + rebuild + ship
- `grep` the rendered docs: no stray German remains EXCEPT the protected step-1 anchors (list them in your report).
- `python3 tools/cas_check.py` = **63/63** (no anchor lost). `mkdocs build -f docs/mkdocs.yml --strict` exit 0. Em-dash grep zero.
- Rebuild: `python3 tools/build_pdf.py`. Open the PDF; confirm cover, TOC ("Contents"), the English Summary, the chapter headings, and the declaration page render in English and diagrams render.
- `/ship`; auto-merge on the green-contract.

## Done means
The PDF reads as a fully English thesis, with only the rubric-citation anchors kept in German (listed in your report), `cas_check` 63/63, CI green, merged, PDF rebuilt. Report the protected anchors and any FFHS-class label that could not be Englished from the preamble. Curate the journal entry.
