"""Phase 4 training-data inventory: earlier BAG commentaries against the frozen 2026 corpus.

Implements the counting rules of ``docs/evidence/2026-11-23-phase4-training-data-inventory.md``,
fixed before any count. The earlier commentaries pinned in ``data/manifests/bag-al-2024-2025.json``
are parsed by the pilot's corpus builder unchanged; their non-introduction sections are grouped
into change families by shared position codes or named projects; every family that shares a code
or a project with the 2026 material is dropped as a whole; then the usable passages of the
remaining families are counted against the proposed threshold of 100 passages from 10 families.

Read-only and offline: the e5 tokenizer counts tokens for the 256-token budget, as for the frozen
corpus; nothing is embedded, no provider or network is used, and the frozen corpus and every
recorded result stay unchanged. Only public material is read (the BAG commentaries and the frozen
2026 record): no evaluation case, gold evidence or answer. The result record holds IDs, hashes,
codes, projects and counts, never passage text.

The e5 model is read from the local Hugging Face cache only (offline mode is forced and checked),
and an existing output file is never replaced:

    UV_PROJECT_ENVIRONMENT="${TMPDIR:-/tmp}/tarifhub-commentary-venv" uv run \\
        --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python tools/commentary_rag/training_inventory.py --out <a new file>

With ``--older-commentaries <commentary-source manifest>`` (read by ``corpus.build_commentaries``)
the record holds three views instead, each a full report keyed by source ID: the four
commentaries above (baseline), the older commentaries alone, and both combined, their families
rebuilt across every source and excluded against the same 2026 reference. It also lists each
passage of the baseline and of the older view whose eligibility the combination changes, and why. These views add two
sensitivities on the printed subsections that the parser files under their parent section
(``OLDER_SENSITIVITIES``); the four-document record keeps its seven.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import corpus

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OLDER = REPO / "data" / "manifests" / "bag-al-2024-2025.json"
REFERENCE = REPO / "data" / "manifests" / "bag-al.json"
RECORD = HERE / "results" / "2026-11-14-retrieval-corrected.json"
RULES = "docs/evidence/2026-11-23-phase4-training-data-inventory.md#rules-fixed-before-counting"
TOKEN_BUDGET = 256  # the frozen 2026 corpus's budget
MIN_PASSAGES = 100  # the proposed threshold: a design choice of this project
MIN_FAMILIES = 10

CODE = re.compile(r"\b(\d{4}\.\d{2})\b")
SERIES = re.compile(r"\b(\d{4})\.(\d{2})\s*ff\.")
WILDCARD = re.compile(r"\b[xX]{4}\.(\d{2})\b")
INTRODUCTION = "einleitung"
# Rule 5: the named projects with their spellings. transAL's phases share one name unless a
# sensitivity keeps them apart; the AL handbook is a document and counts only in its sensitivity.
# transAL1 and transAL2 are its phases as text extraction spells them, the hyphen lost.
PROJECTS = (
    ("transAL", re.compile(r"\btransAL(?:-?[12])?\b")),
    ("Runder Tisch", re.compile(r"\bRunde[nr]?\s+Tisch(?:es)?\b")),
    ("StAR", re.compile(r"\bStrategie\s+Antibiotikaresistenzen\b|\bStAR\b")),
)
HANDBOOK = ("AL handbook", re.compile(r"\bHandbuch\w*"))
NGRAM = 8  # duplicate check: word 8-grams of an older passage found in one 2026 passage
NEAR_DUPLICATE = 0.5


@dataclass(frozen=True)
class Misfiled:
    """Text the page inspection found filed under a section it does not belong to."""

    passage_id: str
    belongs_to: str
    text: str
    found: str


@dataclass(frozen=True)
class Unusable:
    """A passage whose text the page inspection found lost or garbled (rule 3)."""

    passage_id: str
    reason: str


# Found by the page inspection of 2026-11-23 (pdfplumber layout probe and renders of all 21
# pages): one misfiled footnote, no text lost or garbled.
UNUSABLE: tuple[Unusable, ...] = ()
MISFILED = (
    Misfiled(
        passage_id="2025-01-01/p3/s2.3/1",
        belongs_to="2.1",
        text=(
            "1 Vgl. www.bag.admin.ch > Versicherungen Krankenversicherung > Leistungen und "
            "Tarife > Analysenliste (AL) > Dokumente > Faktenblatt vom Juli 2015 zur "
            "Unterteilung der Laboranalysen in Basis- und Spezialanalysen."
        ),
        found="footnote 1 of page 3, referenced in section 2.1, follows section 2.3 in the text",
    ),
)


@dataclass(frozen=True)
class Subsection:
    """Text of a printed subsection (``section``) that the parser files under its parent section.

    Rule 2 keeps the section as the parser files it: the text stays usable in its passage and
    counts under the parser's section in the primary count and in every original sensitivity.
    Only the views of the older commentaries read it otherwise: ``printed_sections`` groups it
    under ``<source>/<section>``, ``subsections_misfiled`` reads it as misfiled text (rule 3).
    """

    passage_id: str
    section: str
    text: str
    found: str


# Found by the page inspection of the older commentaries (2026-11-23; renders, Poppler lines and
# the layout probe): subsection headings the parser does not read. 2022-01-01 and 2023-07-01
# combine several subsections in section 2; in 2023-01-01-urgent and 2023-03-01, 2.1 is the only
# subsection of section 2, so only its label differs.
SUBSECTIONS: tuple[Subsection, ...] = (
    Subsection(
        "2022-01-01/p3/s2/1",
        "2.1",
        (
            "2.1. SARS-CoV-2: Änderungen der Position 3186.00 und Aufnahme der "
            "Positionen 3188.00 für die Genotypisierung des SARS-CoV-2 und 3189.00 "
            "Antikörper gegen SARS-CoV-2 Die Covid-19-Verordnung 3, in der die "
            "Kostenübernahme von Laboranalysen auf SARS-CoV-2 geregelt ist, ist zurzeit "
            "bis zum 31. Dezember 2021 befristet (Stand 29.11.2021). Ab dem Tag, an "
            "welchem die epidemiologische Lage die Aufhebung der Covid-19-Verordnung 3 "
            "erlaubt, ist vorgesehen, dass die Analysen auf SARS-CoV-2 durch die "
            "obligatorische Krankenpflegeversicherung (OKP) nach Bundesgesetz über die "
            "Krankenversicherung (KVG; SR 832.10) übernommen werden."
        ),
        (
            "printed heading \"2.1.\" (page 3) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p3/s2/2",
        "2.1",
        (
            "Das eidgenössische Departement des Innern hat somit für die Situation nach "
            "der Pandemie folgende Anpassungen der Analysenliste entschieden: − Die "
            "Position SARS-CoV-2-RNA-Amplifikation (3186.00) wird für die Diagnose von "
            "Covid-19, mit an die Situation nach der Pandemie angepassten Limitationen, "
            "beibehalten. − 2 Positionen werden neu, mit an die Situation nach der "
            "Pandemie angepassten Limitationen, aufgenommen: - 3188.00 "
            "«SARS-Coronavirus-2 (SARS-CoV-2), Genotypisierung» und - 3189.00 "
            "«SARS-Coronavirus-2 (SARS-CoV-2), Ig oder IgG». Während der Geltungsdauer "
            "der Covid-19-Verordnung 3 (SR 818.101.24) dürfen die Analysen auf "
            "SARS-CoV-2 nicht mittels Analysenliste-Positionen verrechnet werden, wie in "
            "Artikel 26b, Absatz 2 der Covid-19-Verordnung 3 verankert ist."
        ),
        (
            "printed heading \"2.1.\" (page 3) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p3/s2/3",
        "2.1",
        (
            "Diese Regelung steht ausdrücklich in den Limitationen der 3 "
            "Analysenliste-Positionen."
        ),
        (
            "printed heading \"2.1.\" (page 3) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p3/s2/3",
        "2.2",
        (
            "2.2. 1734.00 und 1734.01 «Troponin, T oder I»: Änderungen der Limitationen "
            "Die Messung des kardialen Troponins ist für die Diagnose eines akuten "
            "Myokardinfarkts erforderlich. Gemäss den europäischen Richtlinien und den "
            "nationalen Empfehlungen soll Troponin mit sensitiven bis hochsensitiven "
            "Methoden gemessen werden, da diese besser geeignet sind, Herzinfarkte zu "
            "diagnostizieren. Da es auf dem Markt Troponin-Messgeräte mit sehr "
            "unterschiedlicher Sensitivität und Leistungsfähigkeit gibt, werden die "
            "Positionen 1734.00 und 1734.01 dem aktuellen Stand von Wissenschaft und"
        ),
        (
            "printed heading \"2.2.\" (page 3) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p4/s2/1",
        "2.2",
        (
            "Technik angepasst, indem die Mindestanforderungen an die Messmethoden, die "
            "zu Lasten der obligatorischen Krankenpflegeversicherung (OKP) verrechnet "
            "werden dürfen, präzisiert werden. Für medizinische Laboratorien (Position "
            "1734.00) sind hochsensitive Messmethoden auf dem Markt verfügbar und werden "
            "eingesetzt. Die Leistungslimitationen für die Kostenübernahme der Position "
            "1734.00 durch die OKP treten am 1. Januar 2022 in Kraft. Für "
            "Praxislaboratorien (Position 1734.01) kommen ebenfalls hochsensitive "
            "Messmethoden auf den Markt. Ihre Implementierung in den Praxislaboratorien "
            "erfordert jedoch eine Anpassungszeit."
        ),
        (
            "printed heading \"2.2.\" (page 3) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p4/s2/2",
        "2.2",
        (
            "Daher ist in Position 1734.01 eine zweijährige Übergangsregelung, die am 1. "
            "Januar 2022 in Kraft tritt, vorgesehen."
        ),
        (
            "printed heading \"2.2.\" (page 3) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p4/s2/2",
        "2.3",
        (
            "2.3. 3093:00 «HIV-Resistenz gegen antiretrovirale Substanzen»: Änderungen "
            "der Limitationen Die Beschränkung der Verrechnung zu Lasten der "
            "obligatorischen Krankenpflegeversicherung auf 4 Laboratorien bei der "
            "Position 3093.00 «HIV-Resistenz gegen antiretrovirale Substanzen» steht im "
            "Widerspruch zur Wettbewerbsneutralität des Bundes und ist aus Sicht der "
            "Qualitätssicherung nicht mehr sinnvoll. Sie wird daher aus der Position "
            "3093.00 gestrichen. Diese Änderungen treten per 1. Januar 2022 in Kraft."
        ),
        (
            "printed heading \"2.3.\" (page 4) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p4/s2/2",
        "2.4",
        "2.4.",
        (
            "printed heading \"2.4.\" (page 4) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p4/s2/3",
        "2.4",
        (
            "Erweiterung der Positionen 1674.00 «Spermiocytogramm», 1177.10 "
            "«Autoantikörper gegen Spermien» und 1762.00 "
            "«Zell-/Zellbestandteil-Separation (Percoll-Test)» auf Laboratorien der "
            "Gynäkologie und Geburtshilfe mit Schwerpunkt Reproduktion und "
            "gynäkologischer Endokrinologie und Streichen des Weiterbildungstitels der "
            "Dermatologie und Venerologie bei den Positionen 1427.00 «Hypoosmotischer "
            "Schwelltest», 1597.00 «Penetrationstest» 1673.00 «Spermiennachweis nach "
            "Vasektomie» und 1674.00 «Spermiocytogramm»: Bei der Sterilität gehören "
            "parallel zur Untersuchung der Frau auch die Analysen der Samenprobe. Werden "
            "diese Analysen im reproduktionsmedizinischen Laboratorium durchgeführt, "
            "kann dadurch ein Zeitgewinn erzielt werden, was für die Therapie essentiell "
            "ist. Die Positionen 1674.00, 1177.10 und 1762.00 werden unter strickten "
            "Bedingungen auf die Laboratorien Gynäkologie und Geburtshilfe mit "
            "Schwerpunkt Reproduktion und gynäkologischer Endokrinologie erweitert."
        ),
        (
            "printed heading \"2.4.\" (page 4) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p4/s2/4",
        "2.4",
        (
            "Da die Andrologie nicht mehr Teil des Weiterbildungsprogramms für den "
            "Facharzttitel Dermatologie und Venerologie ist, werden die Positionen "
            "1427.00, 1597.00, 1673.00 und 1674.00 für die Ärzte und Ärztinnen mit dem "
            "Weiterbildungstitel Dermatologie und Venerologie gestrichen. Diese "
            "Änderungen treten per 1. Januar 2022 in Kraft."
        ),
        (
            "printed heading \"2.4.\" (page 4) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2022-01-01/p4/s2/4",
        "2.5",
        (
            "2.5. Anpassung der immunhämatologischen Positionen an die neue Fassung des "
            "Referenzdokuments Die Positionen 1012.00, 1013.00, 1288.00, 1653.00, "
            "1744.00 und 1745.00 werden an die neue Fassung des Referenzdokuments "
            "angepasst, die ab dem 1. Februar 2022 für die Durchführung dieser Analysen "
            "massgebend ist. Die Verwendung der internationalen Blutgruppenterminologie "
            "in dieser Fassung des Referenzdokuments macht eine Anpassung der "
            "Bezeichnung der oben genannten Positionen, sowie der Positionen 1283.00, "
            "1292.00, 6603.50, 6603.51, 6603.54 und 6604.50, erforderlich."
        ),
        (
            "printed heading \"2.5.\" (page 4) with a trailing dot, which the parser does "
            "not read"
        ),
    ),
    Subsection(
        "2023-07-01/p3/s2/1",
        "2.1",
        (
            "2.1 Neuaufnahme der Positionen 3565.00 und 3566.00 Bakterielle DNA (16S "
            "rRNA Gen) Die Identifikation des Erregers ist besonders bei schweren "
            "Infektionen (wie zum Beispiel Infektionen von Herzklappen oder Prothesen) "
            "von grosser Wichtigkeit für den Therapieentscheid und den Therapieerfolg. "
            "Die Bakterienkultur ist die Basis für die Identifikation der Bakterien und "
            "für die Resistenzprüfung. Beide sind für eine gezielte Behandlung "
            "notwendig. Eine besondere Herausforderung besteht, wenn in der Kultur keine "
            "Bakterien nachgewiesen werden können. Die bakterielle Breitspektrum-PCR "
            "(Bakterielle DNA (16S rRNA Gen)) amplifiziert die DNA von bakteriellen "
            "Krankheitserregern. Bei positivem Resultat können anschliessend mittels "
            "Sequenzierung die Bakterien identifiziert werden. Im Gegensatz zur "
            "Bakterienkultur, welche nur lebende Bakterien nachweisen kann, können mit "
            "diesem Verfahren auch Bakterien nachgewiesen werden, die durch eine "
            "Antibiotika-Behandlung abgestorben sind oder aus anderen Gründen mit den "
            "üblichen Kulturmethoden nicht nachweisbar sind."
        ),
        (
            "heading number \"2.1\" (page 3) on a Poppler line of its own, which the "
            "parser does not read"
        ),
    ),
    Subsection(
        "2023-07-01/p3/s2/2",
        "2.1",
        (
            "Die Breitspektrum-PCR liefert zwar keine Resistenzprüfung, jedoch "
            "ermöglicht die Kenntnis der Identität der Erreger Rückschlüsse auf deren "
            "Antibiotika-Empfindlichkeit und kann so zur Verbesserung von Therapie und "
            "Therapieerfolg beitragen. Die bakterielle Breitspektrum-PCR ersetzt die "
            "bakterielle Kultur nicht, sondern sie ergänzt diese. Gemäss dem aktuellen "
            "Stand des Wissens ist die Analyse nur bei Kultur negativen Proben aus "
            "primär sterilen Körperkompartimenten gerechtfertigt. Um die Anwendung "
            "dieser Analyse auf die relevantesten klinischen Situationen zu beschränken, "
            "wird sie auf einen negativen Bakterienkulturnachweis nach zwei Tagen "
            "eingeschränkt. Die Analyse Bakterielle DNA (16S rRNA Gen) kommt meistens im "
            "stationären Setting zur Anwendung, kann aber manchmal auch im ambulanten "
            "Bereich notwendig sein. In der Schweiz wird sie bereits seit vielen Jahren "
            "im stationären Bereich eingesetzt, wo sie unter die DRG-Fallpauschale "
            "fällt. Mit der Aufnahme auf die Analysenliste kann die Bakterielle DNA (16S "
            "rRNA Gen) auch im ambulanten Bereich zu Lasten der obligatorischen "
            "Krankenpflegeversicherung verrechnet werden."
        ),
        (
            "heading number \"2.1\" (page 3) on a Poppler line of its own, which the "
            "parser does not read"
        ),
    ),
    Subsection(
        "2023-07-01/p3/s2/3",
        "2.1",
        "Die beiden neuen Positionen treten per 1. Juli 2023 in Kraft.",
        (
            "heading number \"2.1\" (page 3) on a Poppler line of its own, which the "
            "parser does not read"
        ),
    ),
    Subsection(
        "2023-07-01/p3/s2/3",
        "2.2",
        (
            "2.2 Position 6605.64 Molekulare Genotypisierung humaner leukozytärer "
            "Antigene (human leucocyte antigen, HLA), Lokus A, B, C, DRB1, DRB3/4/5, "
            "DQA1, DQB1, DPA1 und DPB1: endgültige Evaluation der Aufnahme in die AL Am "
            "1. Juli 2021 wurde die Position 6605.64 befristet bis zum 30. Juni 2023 in "
            "die AL aufgenommen, da aufgrund der Covid-19-Pandemie bestimmte "
            "Informationen, die für einen endgültigen Entscheid erforderlich sind, nicht "
            "gesammelt werden konnten."
        ),
        (
            "heading number \"2.2\" (page 3) on a Poppler line of its own, which the "
            "parser does not read"
        ),
    ),
    Subsection(
        "2023-07-01/p4/s2/1",
        "2.2",
        (
            "Die Typisierung humaner leukozytärer Antigene (HLA-Typisierung) wird "
            "hauptsächlich bei allogenen hämatopoetischen Stammzelltransplantationen und "
            "bei Transplantationen solider Organe durchgeführt. Der Erfolg einer "
            "Transplantation hängt unter anderem vom Grad der Kompatibilität zwischen "
            "Spender/-in und Empfänger/-in ab. Ein hoher Kompatibilitätsgrad ermöglicht "
            "eine Reduzierung der mit der Transplantation verbundenen Komplikationen, "
            "der Transplantatabstossungen und der Rezidive. Die molekulare "
            "HLA-Typisierung (Position 6605.64) leistet einen wichtigen Beitrag zur "
            "Erhöhung des Kompatibilitätsgrades zwischen Spender/-in und Empfänger/-in "
            "und ersetzt tendenziell die serologische HLA-Typisierung (Positionen "
            "1419.00 und 1420.00). Ausserdem bestimmt der Transplantationskontext den "
            "Grad der Auflösung der HLA-Typisierung (niedrig bis mittel versus hoch)."
        ),
        (
            "heading number \"2.2\" (page 3) on a Poppler line of its own, which the "
            "parser does not read"
        ),
    ),
    Subsection(
        "2023-07-01/p4/s2/2",
        "2.2",
        (
            "Die Position 6605.64 wird wie folgt geändert: - Sie ist nicht mehr mit den "
            "Positionen zur serologischen HLA-Typisierung (1419.00 und 1420.00) "
            "kumulierbar, und - Der Auflösungsgrad wird bei der maximalen Anzahl der "
            "Male berücksichtigt, die die Position 6605.64 pro Primärprobe verrechnet "
            "werden kann (max. 9 bei niedriger bis mittlerer Auflösung bzw. 14 bei hoher "
            "Auflösung). Die so geänderte Position 6605.64 tritt am 1. Juli 2023 in "
            "Kraft."
        ),
        (
            "heading number \"2.2\" (page 3) on a Poppler line of its own, which the "
            "parser does not read"
        ),
    ),
    Subsection(
        "2023-07-01/p4/s2/2",
        "2.3",
        (
            "Position 3188.00 SARS-Coronavirus-2 (SARS-CoV-2), Genotypisierung: Änderung "
            "betreffend die klinischen Situationen, in denen zu Lasten der OKP "
            "verrechnet werden darf 2.3 Da die Kosten der Analysen auf SARS-CoV-2 bis "
            "zum 31. Dezember 2022 im Rahmen der Covid-19Verordnung 3 vom Bund "
            "übernommen wurden, traten die am 1. Januar 2022 in die AL aufgenommenen "
            "Positionen zu SARS-CoV-2 de facto am 1. Januar 2023 (Datum der Aufhebung "
            "der Kostenübernahme durch den Bund) in Kraft."
        ),
        (
            "heading number \"2.3\" (page 4) after its heading text in the Poppler text, "
            "which the parser does not read"
        ),
    ),
    Subsection(
        "2023-07-01/p4/s2/3",
        "2.3",
        (
            "Die Übernahme der Position 3188.00 durch die obligatorische "
            "Krankenpflegeversicherung (OKP) war bisher bei Reinfektion oder "
            "SARS-CoV2-Infektion nach Impfung, schwerem oder ungewöhnlichem klinischen "
            "Verlauf der SARS-CoV-2-Infektion und/oder Verdacht auf Resistenz auf ein "
            "antivirales Medikament indiziert."
        ),
        (
            "heading number \"2.3\" (page 4) after its heading text in the Poppler text, "
            "which the parser does not read"
        ),
    ),
    Subsection(
        "2023-07-01/p4/s2/4",
        "2.3",
        (
            "Im Zeitraum vom 1. Januar 2022 bis zum 1. Januar 2023 haben sich die "
            "Epidemiologie und die Behandlung (Analysen, Therapien) der "
            "SARS-CoV-2-Infektion stark verändert, so dass es notwendig wurde, die "
            "klinischen Situationen zu anzupassen, in denen die Position 3188.00 von den "
            "Laboratorien verrechnet werden darf: - Bei SARS-CoV2-Reinfektion oder "
            "SARS-CoV2-Infektion nach Impfung ist keine Genotypisierung mehr "
            "erforderlich, da diese Situationen zur Norm geworden sind. - Es gibt neue "
            "Therapiemodalitäten gegen SARS-CoV-2 Diese Änderungen tangieren den Umstand "
            "nicht, dass die Position 3188.00 bis zum 31. Dezember 2023 befristet ist, "
            "damit dann entschieden werden kann, ob sie nach diesem Datum weiterhin in "
            "der AL stehen soll. Diese Änderungen der Position 3188.00 treten am 1. Juli "
            "2023 in Kraft."
        ),
        (
            "heading number \"2.3\" (page 4) after its heading text in the Poppler text, "
            "which the parser does not read"
        ),
    ),
    Subsection(
        "2023-01-01-urgent/p3/s2/1",
        "2.1",
        (
            "2.1 Anpassung der Limitationen der Positionen 3186.00 SARS-Coronavirus-2 "
            "(SARS-CoV-2), 1 Keim oder 1. Keim; 3186.10 SARS-Coronavirus-2 (SARS-CoV2), "
            "zusätzlicher Keim; 3188.00 SARS-Coronavirus-2 (SARS-CoV-2), "
            "Genotypisierung; 3189.00 SARS-Coronavirus-2 (SARS-CoV-2), Ig oder IgG; "
            "4700.00 Auftragstaxe; 4707.00 Präsenztaxe In der Wintersession 2022 hat das "
            "Parlament die Bestimmung im Covid-19-Gesetz zur Übernahme der Kosten der "
            "Covid-Analysen durch den Bund nicht verlängert. Entsprechend besteht ab dem "
            "1. Januar 2023 keine rechtliche Grundlage mehr für eine Kostenübernahme von "
            "Analysen auf Sars-CoV-2 durch den Bund. Die Kosten der Analysen auf "
            "Sars-CoV-2 gehen ab dem 1. Januar 2023 grundsätzlich zulasten der "
            "getesteten Person."
        ),
        (
            "heading number \"2.1\" (page 3) on a Poppler line of its own, which the "
            "parser does not read; 2.1 is the only subsection of section 2"
        ),
    ),
    Subsection(
        "2023-01-01-urgent/p3/s2/2",
        "2.1",
        (
            "Bei Symptomen, die mit Covid-19 vereinbar sind und sofern die Analyse eine "
            "medizinisch-therapeutische Konsequenz zur Folge hat, übernimmt die "
            "obligatorische Krankenpflegeversicherung (OKP) auf individuelle ärztliche "
            "Anordnung die Kosten der Analysen auf Sars-CoV-2 bei ambulanter "
            "Durchführung gemäss Analysenliste (AL; Anhang 3 der "
            "Krankenpflege-Leistungsverordnung). Die Covid-19-Analysen "
            "(Molekularbiologie, Serologie und Antikörper) waren bereits in der "
            "Analysenliste aufgeführt, jedoch mit der Limitation, dass diese während der "
            "Geltungsdauer der Covid-19-Verordnung 3 nicht gemäss Analysenliste in "
            "Rechnung gestellt werden können."
        ),
        (
            "heading number \"2.1\" (page 3) on a Poppler line of its own, which the "
            "parser does not read; 2.1 is the only subsection of section 2"
        ),
    ),
    Subsection(
        "2023-01-01-urgent/p3/s2/3",
        "2.1",
        (
            "Da die Covid-19-Verordnung 3 mit gewissen Massnahmen zur Pandemiebekämpfung "
            "weiterhin bestehen bleibt, werden die Limitationen im Zusammenhang mit der "
            "Geltungsdauer der Covid-19-Verordnung 3 bei den Positionen 3186.00 "
            "SARS-Coronavirus-2 (SARS-CoV-2), 1 Keim oder 1. Keim; 3186.10 "
            "SARS-Coronavirus-2 (SARS-CoV2), zusätzlicher Keim; 3188.00 "
            "SARS-Coronavirus-2 (SARS-CoV-2), Genotypisierung; 3189.00 SARSCoronavirus-2 "
            "(SARS-CoV-2), Ig oder IgG; 4700.00 Auftragstaxe; 4707.00 Präsenztaxe per 1. "
            "Januar 2023 gestrichen."
        ),
        (
            "heading number \"2.1\" (page 3) on a Poppler line of its own, which the "
            "parser does not read; 2.1 is the only subsection of section 2"
        ),
    ),
    Subsection(
        "2023-03-01/p3/s2/1",
        "2.1",
        (
            "2.1 Neue Positionen 3191.00 und 3191.10 Affenpockenvirus (Monkeypox virus) "
            "Die Affenpocken sind eine Krankheit, die normalerweise von Tieren auf "
            "Menschen übertragen wird und für Einzelfälle und kleine Epidemien in Afrika "
            "verantwortlich ist. Seit Anfang Mai 2022 gibt es in vielen Ländern "
            "ausserhalb Afrikas einen aussergewöhnlichen Ausbruch mit Übertragung von "
            "Mensch zu Mensch, den die WHO zu einer gesundheitlichen Notlage von "
            "internationaler Tragweite erklärt hat. Bisher sind in der Schweiz keine "
            "Todesfälle bekannt. Die Affenpocken sind eine fieberhafte Erkrankung mit "
            "mehr oder weniger ausgedehntem und lokalisiertem Hautausschlag. Betroffen "
            "ist vor allem die Gemeinschaft der Männer, die Sex mit Männern haben. Der "
            "Verlauf ist schmerzhaft und langwierig, aber in der Regel harmlos. "
            "Risikofaktoren für einen schweren Verlauf sind Immunschwäche, niedriges "
            "Alter und Schwangerschaft."
        ),
        (
            "heading number \"2.1\" (page 3) on a Poppler line of its own, which the "
            "parser does not read; 2.1 is the only subsection of section 2"
        ),
    ),
    Subsection(
        "2023-03-01/p3/s2/2",
        "2.1",
        (
            "Die Diagnose erfolgt durch den molekularbiologischen Nachweis des "
            "Affenpockenvirus mittels einer Echtzeit-Polymerase-Kettenreaktion (PCR). "
            "Die Kostenübernahme der Analysen durch die obligatorische "
            "Krankenpflegeversicherung (OKP) ist auf diagnostische Analysen und "
            "Nachuntersuchungen bei symptomatischen Patientinnen und Patienten "
            "beschränkt. Sie umfasst keine Analysen, die aus epidemiologischen Gründen "
            "(z. B. symptomfreie Kontaktfälle) oder aus Spitalhygienischen Gründen "
            "durchgeführt werden. Im Hinblick auf die Kostenübernahme durch die OKP ist "
            "zu beachten, dass die Kostenbeteiligung (Franchise und Selbstbehalt) gilt. "
            "Diese neuen Positionen treten am 1. März 2023 in Kraft."
        ),
        (
            "heading number \"2.1\" (page 3) on a Poppler line of its own, which the "
            "parser does not read; 2.1 is the only subsection of section 2"
        ),
    ),
)


@dataclass(frozen=True)
class Unresolved:
    """A commentary source whose pages the inspection cannot verify or parse reliably.

    Its passages are left out of every count and grouping; the record lists the source under
    ``unresolved`` instead of counting it as zero.
    """

    source_id: str
    reason: str


# Found by the page inspection of the older commentaries (2026-11-23): two documents without a
# numbered heading, from which the unchanged parser yields no passage.
UNRESOLVED: tuple[Unresolved, ...] = (
    Unresolved(
        "2021-02-01",
        "no numbered heading: the unchanged parser starts no section, drops the body text of "
        "page 3 as front matter and yields no passage",
    ),
    Unresolved(
        "2021-07-01",
        "no numbered heading: the unchanged parser starts no section, drops the body text of "
        "pages 3 and 4 as front matter and yields no passage",
    ),
)


@dataclass(frozen=True)
class Options:
    """One application of the rules: the primary count or one sensitivity."""

    phases_apart: bool = False  # transAL-1 and transAL-2 as two projects
    handbook: bool = False  # the AL handbook as a named item
    ranges: bool = (
        False  # 'A ff.' series and 'xxxx.dd' wildcards against the 2026 codes
    )
    strict_misfiled: bool = False  # drop every passage that carries misfiled text
    no_exclusion: bool = False  # the upper bound: no family is dropped
    printed_sections: bool = False  # group Subsection text under its printed section
    subsections_misfiled: bool = False  # read Subsection text as misfiled text (rule 3)


SENSITIVITIES = {
    "primary": Options(),
    "misfiled_strict": Options(strict_misfiled=True),
    "ranges": Options(ranges=True),
    "transal_phases_apart": Options(phases_apart=True),
    "handbook_named": Options(handbook=True),
    "strictest": Options(strict_misfiled=True, ranges=True, handbook=True),
    "no_exclusion": Options(no_exclusion=True),
}
# The views of the older commentaries add two readings of the printed subsections that the
# parser files under their parent section; the four-document record keeps SENSITIVITIES.
OLDER_SENSITIVITIES = {
    **SENSITIVITIES,
    "printed_sections": Options(printed_sections=True),
    "subsections_misfiled": Options(subsections_misfiled=True),
}
NEWER_SWITCHES = ("printed_sections", "subsections_misfiled")


def _switches(options: Options) -> dict:
    """The options as a record lists them: the five original switches always, a newer one only
    when it is on, so that the four-document record keeps its form."""

    return {k: v for k, v in options.__dict__.items() if v or k not in NEWER_SWITCHES}


def codes(text: str) -> set[str]:
    """Explicit position codes (``dddd.dd``), the frozen rule."""

    return set(CODE.findall(text))


def _phase(spelling: str) -> str:
    """A transAL phase in one form: transAL2 and transAL-2 are transAL-2; transAL stays."""

    return f"transAL-{spelling[-1]}" if spelling[-1] in "12" else spelling


def projects(text: str, options: Options | None = None) -> set[str]:
    """The named projects of rule 5 that ``text`` mentions."""

    options = options or Options()
    found = set()
    for name, pattern in PROJECTS:
        for match in pattern.finditer(text):
            found.add(
                _phase(match.group(0)) if options.phases_apart and name == "transAL" else name
            )
    if options.handbook and HANDBOOK[1].search(text):
        found.add(HANDBOOK[0])
    return found


def range_overlaps(text: str, reference_codes: set[str]) -> set[str]:
    """The 2026 codes an ``A ff.`` series or an ``xxxx.dd`` wildcard in ``text`` reaches."""

    hits = set()
    for stem, decimals in SERIES.findall(text):
        start = f"{stem}.{decimals}"
        hits |= {c for c in reference_codes if c[:4] == stem and c >= start}
    for decimals in WILDCARD.findall(text):
        hits |= {c for c in reference_codes if c[5:] == decimals}
    return hits


def _order(key: str) -> tuple[str, tuple[int, ...]]:
    edition, number = key.split("/")
    return edition, tuple(int(part) for part in number.split("."))


def families(sections: Mapping[str, tuple[set[str], set[str]]]) -> list[list[str]]:
    """Group sections (key → codes, projects) that share a code or a project, transitively.

    A section with neither stays a family of its own. Families come in the order of their first
    section, each listing its sections in edition and section order.
    """

    keys = sorted(sections, key=_order)
    parent = {key: key for key in keys}

    def root(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    owner: dict[tuple[str, str], str] = {}
    for key in keys:
        found, named = sections[key]
        for item in sorted(
            {("code", c) for c in found} | {("project", p) for p in named}
        ):
            if item in owner:
                parent[root(key)] = root(owner[item])
            else:
                owner[item] = key
    groups: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        groups[root(key)].append(key)
    return sorted(groups.values(), key=lambda group: _order(group[0]))


def _grams(text: str) -> set[tuple[str, ...]]:
    words = corpus.normalize(text).split(" ")
    return {tuple(words[i : i + NGRAM]) for i in range(len(words) - NGRAM + 1)}


def duplicates(
    older: Iterable[corpus.Passage], reference: Iterable[corpus.Passage]
) -> list[dict]:
    """Older passages whose text equals a 2026 passage or lies mostly inside one (rule 10)."""

    kept = [(p, _grams(p.text)) for p in reference]
    found = []
    for p in older:
        grams = _grams(p.text)
        for q, other in kept:
            same = p.text_sha256 == q.text_sha256
            share = len(grams & other) / len(grams) if grams else 0.0
            if same or share >= NEAR_DUPLICATE:
                found.append(
                    {
                        "passage_id": p.passage_id,
                        "reference_passage_id": q.passage_id,
                        "same_text": same,
                        "share_of_8grams": round(share, 4),
                    }
                )
    return found


def _key(p: corpus.Passage) -> str:
    if p.section is None:
        raise ValueError(
            f"{p.passage_id}: a passage without a section cannot be grouped"
        )
    return f"{p.edition}/{p.section}"


def _introduction(p: corpus.Passage) -> bool:
    return (p.section_title or "").strip().lower().startswith(INTRODUCTION)


def _names(text: str, options: Options) -> bool:
    """Whether ``text`` names a position code or a named project (rules 4 and 5)."""

    return bool(codes(text) or projects(text, options))


def _subsection_problem(p: corpus.Passage | None, item: Subsection) -> str | None:
    """Why a Subsection does not fit its passage, or None: the passage must hold the text, and
    the section must be a subsection of the parser's section (``<parser section>.<n>``)."""

    if p is None or item.text not in p.text:
        return f"subsection text of {item.passage_id} not found in that passage"
    if p.section is None or not re.fullmatch(rf"{re.escape(p.section)}(\.[0-9]+)+", item.section):
        return (
            f"{item.passage_id}: {item.section} is not a subsection of its parser section "
            f"{p.section}"
        )
    return None


def _rest(p: corpus.Passage, items: Iterable[Subsection]) -> str:
    """The text of ``p`` without its Subsection fragments; refuses fragments that overlap."""

    rest = p.text
    for item in items:
        if item.text not in rest:
            raise ValueError(
                f"subsection text of {item.passage_id} ({item.section}) overlaps another "
                "subsection of that passage"
            )
        rest = rest.replace(item.text, " ", 1)
    return rest


def count(  # noqa: PLR0913 - two corpora, the options and three kinds of inspection finding
    older: corpus.Corpus,
    reference: corpus.Corpus,
    options: Options | None = None,
    *,
    misfiled: Iterable[Misfiled] = MISFILED,
    unusable: Iterable[Unusable] = UNUSABLE,
    subsections: Iterable[Subsection] = (),
) -> dict:
    """Apply rules 2 to 10 once: families, exclusion, usable and eligible passages, counts.

    ``subsections`` take effect only in the ``printed_sections`` reading (each fragment counts
    under its printed section) and the ``subsections_misfiled`` reading (their text read as
    misfiled text); every other count takes the passages as the parser files them.
    """

    options = options or Options()
    by_id = {p.passage_id: p for p in older.passages}
    flagged: dict[str, list[Misfiled]] = defaultdict(list)
    for item in misfiled:
        if item.passage_id not in by_id or item.text not in by_id[item.passage_id].text:
            raise ValueError(
                f"misfiled text of {item.passage_id} not found in that passage"
            )
        flagged[item.passage_id].append(item)
    lost: dict[str, str] = {}
    for item in unusable:
        if item.passage_id not in by_id:
            raise ValueError(
                f"unusable passage {item.passage_id} not found in the corpus"
            )
        lost[item.passage_id] = item.reason
    fragments: dict[str, list[Subsection]] = defaultdict(list)
    for item in subsections:
        problem = _subsection_problem(by_id.get(item.passage_id), item)
        if problem:
            raise ValueError(problem)
        fragments[item.passage_id].append(item)
    rests = {pid: _rest(by_id[pid], items) for pid, items in fragments.items()}
    copies = {
        found["passage_id"]: found["reference_passage_id"]
        for found in duplicates(older.passages, reference.passages)
    }

    ref_codes: set[str] = set()
    ref_projects: set[str] = set()
    where: dict[tuple[str, str], set[str]] = defaultdict(set)
    for p in reference.passages:
        if _introduction(p):
            continue
        for c in codes(p.text):
            ref_codes.add(c)
            where[("code", c)].add(_key(p))
        for name in projects(p.text, options):
            ref_projects.add(name)
            where[("project", name)].add(_key(p))

    def parts(p: corpus.Passage) -> list[tuple[str, str]]:
        """The (section key, text) parts a passage counts under: the passage whole, or in the
        printed_sections reading its Subsection fragments, each under its printed section, and
        the rest under the parser's section when that rest names a code or a project."""
        if not options.printed_sections or p.passage_id not in fragments or _introduction(p):
            return [(_key(p), p.text)]
        pieces = [(f"{p.edition}/{i.section}", i.text) for i in fragments[p.passage_id]]
        rest = rests[p.passage_id]
        return pieces + ([(_key(p), rest)] if _names(rest, options) else [])

    section_codes: dict[str, set[str]] = defaultdict(set)
    section_projects: dict[str, set[str]] = defaultdict(set)
    section_texts: dict[str, list[str]] = defaultdict(list)
    introductions = set()
    for p in older.passages:
        for key, text in parts(p):
            section_texts[key].append(text)
            section_codes[key] |= codes(text)
            section_projects[key] |= projects(text, options)
        if _introduction(p):
            introductions.add(_key(p))
    grouped = families(
        {
            k: (section_codes[k], section_projects[k])
            for k in section_texts
            if k not in introductions
        }
    )
    family_of = {s: f"F{n:02d}" for n, sections in enumerate(grouped, 1) for s in sections}

    def belongs(p: corpus.Passage) -> str | None:
        """The family of a passage: that of all its parts if they lie in one family (rule 13:
        every Subsection fragment is a part, a remainder only when it names a code or a
        project); None for an introduction and for a passage split across families, which is
        never eligible."""
        found = {family_of.get(k) for k, _ in parts(p)}
        return found.pop() if len(found) == 1 else None

    assigned = {p.passage_id: belongs(p) for p in older.passages}

    def usable(p: corpus.Passage) -> bool:
        """Rule 3: no introduction, no lost or garbled text, and misfiled text only when it
        names no code or project (none in the strict count); in the subsections_misfiled
        reading, Subsection text counts as misfiled text."""
        if _introduction(p) or p.passage_id in lost:
            return False
        items = flagged.get(p.passage_id, [])
        if items and options.strict_misfiled:
            return False
        if options.subsections_misfiled and any(
            _names(i.text, options) for i in fragments.get(p.passage_id, [])
        ):
            return False
        return not any(codes(i.text) or projects(i.text, options) for i in items)

    rows = []
    for n, sections in enumerate(grouped, 1):
        name = f"F{n:02d}"
        passages = [p for p in older.passages if assigned[p.passage_id] == name]  # each once
        found = set().union(*(section_codes[s] for s in sections))
        named = set().union(*(section_projects[s] for s in sections))
        shared_codes = found & ref_codes
        shared_projects = named & ref_projects
        reached = set()
        if options.ranges:
            for s in sections:
                for text in section_texts[s]:
                    reached |= range_overlaps(text, ref_codes)
        touched = set()
        for c in shared_codes | reached:
            touched |= where[("code", c)]
        for name_ in shared_projects:
            touched |= where[("project", name_)]
        excluded = not options.no_exclusion and bool(
            shared_codes or shared_projects or reached
        )
        rows.append(
            {
                "id": name,
                "sections": sections,
                "editions": sorted({s.split("/")[0] for s in sections}),
                "passages": len(passages),
                "usable_passages": sum(usable(p) for p in passages),
                "codes": sorted(found),
                "projects": sorted(named),
                "shared_codes": sorted(shared_codes),
                "shared_projects": sorted(shared_projects),
                "range_codes": sorted(reached),
                "reference_sections": sorted(touched, key=_order),
                "excluded": excluded,
            }
        )
    excluded_families = {r["id"] for r in rows if r["excluded"]}

    passages_out = []
    for p in older.passages:
        family = assigned[p.passage_id]
        ok = usable(p)
        passages_out.append(
            {
                "passage_id": p.passage_id,
                "edition": p.edition,
                "page": p.page,
                "section": p.section,
                "tokens": p.tokens,
                "split": p.split,
                "text_sha256": p.text_sha256,
                "introduction": _introduction(p),
                "misfiled": sorted(
                    {i.belongs_to for i in flagged.get(p.passage_id, [])}
                ),
                "unusable": lost.get(p.passage_id),
                "duplicate_of": copies.get(p.passage_id),
                "family": family,
                "usable": ok,
                "eligible": ok  # rule 8, and rule 10: a copy of 2026 text is never eligible
                and family is not None
                and family not in excluded_families
                and p.passage_id not in copies,
            }
        )

    def tally(rows_in: list[dict]) -> dict:
        fams = {r["family"] for r in rows_in if r["family"] is not None}
        eligible = [r for r in rows_in if r["eligible"]]
        return {
            "passages": len(rows_in),
            "introduction_passages": sum(r["introduction"] for r in rows_in),
            "usable_passages": sum(r["usable"] for r in rows_in),
            "misfiled_passages": sum(bool(r["misfiled"]) for r in rows_in),
            "duplicate_passages": sum(
                r["usable"] and r["duplicate_of"] is not None for r in rows_in
            ),
            "families": len(fams),
            "eligible_families": len({r["family"] for r in eligible}),
            "eligible_passages": len(eligible),
            "excluded_families": len(fams & excluded_families),
            "excluded_passages": sum(
                r["usable"] and r["family"] in excluded_families for r in rows_in
            ),
        }

    by_edition = {
        d.edition: tally([r for r in passages_out if r["edition"] == d.edition])
        for d in older.documents
    }
    overall = tally(passages_out)
    # Overall, the families are the grouped ones: in the printed_sections reading a family can
    # hold only split passages, so that no passage row names it.
    overall["families"] = len(rows)
    overall["excluded_families"] = len(excluded_families)
    return {
        "options": _switches(options),
        "reference_codes": len(ref_codes),
        "reference_projects": sorted(ref_projects),
        "families": rows,
        "passages": passages_out,
        "counts": {"by_edition": by_edition, "overall": overall},
        "threshold": {
            "min_passages": MIN_PASSAGES,
            "min_families": MIN_FAMILIES,
            "met": overall["eligible_passages"] >= MIN_PASSAGES
            and overall["eligible_families"] >= MIN_FAMILIES,
            "shortfall_passages": max(0, MIN_PASSAGES - overall["eligible_passages"]),
            "shortfall_families": max(0, MIN_FAMILIES - overall["eligible_families"]),
        },
    }


def report(  # noqa: PLR0913 - two corpora, three kinds of inspection finding, the sensitivities
    older: corpus.Corpus,
    reference: corpus.Corpus,
    *,
    misfiled: Iterable[Misfiled] = MISFILED,
    unusable: Iterable[Unusable] = UNUSABLE,
    subsections: Iterable[Subsection] = (),
    sensitivities: Mapping[str, Options] = SENSITIVITIES,
) -> dict:
    """The primary count in full, every sensitivity in summary, and the duplicate check.

    The sensitivities are the original seven unless given; the views of the older commentaries
    pass :data:`OLDER_SENSITIVITIES`.
    """

    misfiled, unusable, subsections = tuple(misfiled), tuple(unusable), tuple(subsections)
    findings = {"misfiled": misfiled, "unusable": unusable, "subsections": subsections}
    primary = count(older, reference, **findings)
    summary = {}
    for name, options in sensitivities.items():
        result = primary if name == "primary" else count(older, reference, options, **findings)
        overall = result["counts"]["overall"]
        summary[name] = {
            "options": _switches(options),
            "eligible_passages": overall["eligible_passages"],
            "eligible_families": overall["eligible_families"],
            "excluded_families": overall["excluded_families"],
            "met": result["threshold"]["met"],
        }
    return {
        "rules": RULES,
        "documents": [
            {
                "edition": d.edition,
                "path": d.path,
                "sha256": d.sha256,
                "source_url": d.source_url,
                "title": d.title,
                "pages": d.page_count,
                "excluded_pages": [
                    {"page": e.page, "reason": e.reason}
                    for e in older.excluded_pages
                    if e.edition == d.edition
                ],
            }
            for d in older.documents
        ],
        "unusable": [
            {"passage_id": u.passage_id, "reason": u.reason} for u in unusable
        ],
        "misfiled": [
            {
                "passage_id": m.passage_id,
                "belongs_to": m.belongs_to,
                "found": m.found,
                "names_codes": sorted(codes(m.text)),
                "names_projects": sorted(projects(m.text)),
            }
            for m in misfiled
        ],
        "primary": primary,
        "sensitivities": summary,
        "duplicates": duplicates(older.passages, reference.passages),
    }


SOURCE_NOTE = (
    "Every view counts commentary sources, not editions: the keys of counts.by_edition, the "
    "edition of a passage row, the editions and the section keys (<source ID>/<section>) of a "
    "family and the passage IDs are source IDs. A source ID begins with the source's first "
    "effective date; effective_dates lists every date the source covers. eligibility_changes "
    "compares the baseline and the older view, each alone (the alone_* fields), with the "
    "combined view."
)


def _source(key: str) -> str:
    """The source ID that a passage ID or a section key begins with."""

    return key.split("/", 1)[0]


def _first_date(document: corpus.Document) -> tuple[str, str]:
    return (document.effective_dates or (document.edition,))[0], document.edition


def merge(a: corpus.Corpus, b: corpus.Corpus) -> corpus.Corpus:
    """Both corpora as one: documents, passages and excluded pages in (first effective date,
    source ID) order, each source's own order kept.

    Refuses (ValueError) a source ID, a document (by SHA-256) or a passage ID that occurs more
    than once, passages or excluded pages without their document, and different token budgets
    or model limits.
    """

    problems = []
    if (a.token_budget, a.model_limit) != (b.token_budget, b.model_limit):
        problems.append(
            f"token budget and model limit differ ({a.token_budget}/{a.model_limit} and "
            f"{b.token_budget}/{b.model_limit})"
        )
    documents = (*a.documents, *b.documents)
    passages = (*a.passages, *b.passages)
    excluded = (*a.excluded_pages, *b.excluded_pages)
    for label, values in (
        ("source ID", [d.edition for d in documents]),
        ("document SHA-256", [d.sha256 for d in documents]),
        ("passage ID", [p.passage_id for p in passages]),
    ):
        repeated = sorted(v for v, n in Counter(values).items() if n > 1)
        if repeated:
            problems.append(f"{label} {', '.join(repeated)} occurs more than once")
    order = {d.edition: _first_date(d) for d in documents}
    orphans = sorted({x.edition for x in (*passages, *excluded) if x.edition not in order})
    if orphans:
        problems.append(f"source {', '.join(orphans)} has passages or pages but no document")
    if problems:
        raise ValueError("merge refused: " + "; ".join(problems))
    return corpus.Corpus(
        documents=tuple(sorted(documents, key=_first_date)),
        passages=tuple(sorted(passages, key=lambda p: order[p.edition])),
        excluded_pages=tuple(sorted(excluded, key=lambda e: order[e.edition])),
        token_budget=a.token_budget,
        model_limit=a.model_limit,
    )


def _source_rows(view: corpus.Corpus) -> list[dict]:
    """The document rows of a view, keyed by source ID, with its dates and declared title."""

    return [
        {
            "source_id": d.edition,
            "effective_dates": list(d.effective_dates or (d.edition,)),
            "path": d.path,
            "sha256": d.sha256,
            "source_url": d.source_url,
            "title": d.title,
            "declared_title": d.declared_title,
            "pages": d.page_count,
            "excluded_pages": [
                {"page": e.page, "reason": e.reason}
                for e in view.excluded_pages
                if e.edition == d.edition
            ],
        }
        for d in view.documents
    ]


def _check_findings(
    combined: corpus.Corpus,
    misfiled: tuple[Misfiled, ...],
    unusable: tuple[Unusable, ...],
    subsections: tuple[Subsection, ...],
    unresolved: tuple[Unresolved, ...],
) -> None:
    """Refuse a finding whose source is in no view, or whose passage or text is missing, a
    Subsection that does not fit its passage, and a source that yields no passage but is not
    listed as unresolved (rule 12)."""

    sources = {d.edition for d in combined.documents}
    by_id = {p.passage_id: p for p in combined.passages}
    problems = []
    fitting: dict[str, list[Subsection]] = defaultdict(list)
    for item in (*misfiled, *unusable, *subsections):
        if _source(item.passage_id) not in sources:
            problems.append(f"{item.passage_id}: its source is in none of the views")
        elif item.passage_id not in by_id:
            problems.append(f"{item.passage_id}: passage not found in its source")
        elif isinstance(item, Misfiled) and item.text not in by_id[item.passage_id].text:
            problems.append(f"misfiled text of {item.passage_id} not found in that passage")
        elif isinstance(item, Subsection):
            problem = _subsection_problem(by_id[item.passage_id], item)
            if problem:
                problems.append(problem)
            else:
                fitting[item.passage_id].append(item)
    for passage_id, items in fitting.items():
        try:
            _rest(by_id[passage_id], items)
        except ValueError as exc:
            problems.append(str(exc))
    for source_id, n in Counter(u.source_id for u in unresolved).items():
        if source_id not in sources:
            problems.append(f"unresolved source {source_id} is in none of the views")
        if n > 1:
            problems.append(f"unresolved source {source_id} is listed {n} times")
    held = {p.edition for p in combined.passages}
    for source_id in sorted(sources - held - {u.source_id for u in unresolved}):
        problems.append(
            f"source {source_id} yields no passage: list it in UNRESOLVED after the page "
            "inspection"
        )
    if problems:
        raise ValueError("inspection findings refused: " + "; ".join(problems))


def _view(  # noqa: PLR0913 - a view, the reference and the four kinds of inspection finding
    view: corpus.Corpus,
    reference: corpus.Corpus,
    misfiled: tuple[Misfiled, ...],
    unusable: tuple[Unusable, ...],
    subsections: tuple[Subsection, ...],
    unresolved: tuple[Unresolved, ...],
) -> tuple[dict, corpus.Corpus]:
    """One view: :func:`report` of its resolved sources with their findings and
    :data:`OLDER_SENSITIVITIES`, the document row of every source it holds, and its Subsections
    and unresolved sources listed; and the corpus it counted."""

    held = {d.edition for d in view.documents}
    left_out = [u for u in unresolved if u.source_id in held]
    skipped = {u.source_id for u in left_out}
    counted = corpus.Corpus(
        documents=tuple(d for d in view.documents if d.edition not in skipped),
        passages=tuple(p for p in view.passages if p.edition not in skipped),
        excluded_pages=tuple(e for e in view.excluded_pages if e.edition not in skipped),
        token_budget=view.token_budget,
        model_limit=view.model_limit,
    )
    kept = held - skipped
    marks = [s for s in subsections if _source(s.passage_id) in kept]
    out = report(
        counted,
        reference,
        misfiled=[m for m in misfiled if _source(m.passage_id) in kept],
        unusable=[u for u in unusable if _source(u.passage_id) in kept],
        subsections=marks,
        sensitivities=OLDER_SENSITIVITIES,
    )
    out["documents"] = _source_rows(view)
    out["subsections"] = [
        {
            "passage_id": s.passage_id,
            "section": s.section,
            "found": s.found,
            "names_codes": sorted(codes(s.text)),
            "names_projects": sorted(projects(s.text)),
        }
        for s in marks
    ]
    out["unresolved"] = [{"source_id": u.source_id, "reason": u.reason} for u in left_out]
    return out, counted


def _section_items(passages: Iterable[corpus.Passage]) -> dict[str, set[tuple[str, str]]]:
    """The codes and projects of each non-introduction section, as the primary count reads them."""

    items: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for p in passages:
        if not _introduction(p):
            items[_key(p)] |= {("code", c) for c in codes(p.text)}
            items[_key(p)] |= {("project", name) for name in projects(p.text)}
    return items


def eligibility_changes(
    baseline: corpus.Corpus, combined: corpus.Corpus, before: dict, after: dict
) -> dict:
    """What the merge does to the passages of one view alone, from two primary counts.

    ``before`` and ``after`` are the primary counts (:func:`count`) of ``baseline``, a view
    alone (the four baseline commentaries or the older ones), and of ``combined``, that view
    merged with the other sources. Adding sections can only join
    families, so a baseline passage keeps its usability and every section of its family, and
    its eligibility can only fall, and only where its family grew into an excluded one. Each of
    these is checked, not assumed: counts that break one are refused (ValueError).

    Lists every passage whose eligibility changed and every baseline family whose sections
    grew, with the combined family's sections, the codes and projects it shares with 2026 (what
    excludes it) and the linking codes and projects: those that an older section of the family
    shares with another of its sections.
    """

    old_sources = {d.edition for d in baseline.documents}
    members = {f["id"]: f["sections"] for f in before["families"]}
    merged = {f["id"]: f for f in after["families"]}
    merged_of = {s: f["id"] for f in after["families"] for s in f["sections"]}
    rows = {r["passage_id"]: r for r in after["passages"]}
    problems: list[str] = []
    changed = []
    for row in before["passages"]:
        pid, new = row["passage_id"], rows.get(row["passage_id"])
        if new is None:
            problems.append(f"{pid} is missing from the combined count")
            continue
        old_set = set(members.get(row["family"], ()))
        new_set = set(merged[new["family"]]["sections"]) if new["family"] else set()
        if (row["family"] is None) != (new["family"] is None) or not old_set <= new_set:
            problems.append(f"{pid} lost sections of its family")
        if row["usable"] != new["usable"]:
            problems.append(f"{pid} changed usability")
        if row["eligible"] == new["eligible"]:
            continue
        if new["eligible"]:
            problems.append(f"{pid} became eligible")
        elif old_set == new_set or not merged.get(new["family"], {}).get("excluded"):
            problems.append(f"{pid} lost eligibility in a family that did not grow into an exclusion")
        changed.append(
            {
                "passage_id": pid,
                "alone_family": row["family"],
                "combined_family": new["family"],
                "alone_eligible": row["eligible"],
                "combined_eligible": new["eligible"],
            }
        )
    items = _section_items(combined.passages)
    grown = []
    for family in before["families"]:
        targets = {merged_of.get(s) for s in family["sections"]}
        if len(targets) != 1 or None in targets:
            problems.append(f"baseline family {family['id']} is not one combined family")
            continue
        joined = merged[targets.pop()]
        if set(joined["sections"]) == set(family["sections"]):
            continue
        older_sections = [s for s in joined["sections"] if _source(s) not in old_sources]
        linking = {
            item
            for s in older_sections
            for item in items[s]
            if any(item in items[t] for t in joined["sections"] if t != s)
        }
        grown.append(
            {
                "alone_family": family["id"],
                "alone_sections": family["sections"],
                "combined_family": joined["id"],
                "combined_sections": joined["sections"],
                "added_sections": [s for s in joined["sections"] if s not in family["sections"]],
                "alone_excluded": family["excluded"],
                "combined_excluded": joined["excluded"],
                "excluding_codes": joined["shared_codes"],
                "excluding_projects": joined["shared_projects"],
                "linking_codes": sorted(v for kind, v in linking if kind == "code"),
                "linking_projects": sorted(v for kind, v in linking if kind == "project"),
            }
        )
    if problems:
        raise ValueError("eligibility changes refused: " + "; ".join(problems))
    return {"passages": changed, "families": grown}


def views(  # noqa: PLR0913 - three corpora and the three kinds of inspection finding
    baseline: corpus.Corpus,
    older: corpus.Corpus,
    reference: corpus.Corpus,
    *,
    misfiled: Iterable[Misfiled] = MISFILED,
    unusable: Iterable[Unusable] = UNUSABLE,
    subsections: Iterable[Subsection] = SUBSECTIONS,
    unresolved: Iterable[Unresolved] = UNRESOLVED,
) -> dict:
    """The baseline, the older commentaries and both combined, each in full, and what combining
    them changes.

    Each view is :func:`report` of its own corpus with :data:`OLDER_SENSITIVITIES`, its document
    rows keyed by source ID and its Subsections listed; the combined view rebuilds the families across every source of both and excludes them against
    the same 2026 reference. A finding applies to a view only when its source is in it; one
    whose source is in no view, or whose passage or text is missing, is refused (ValueError).
    The passages of an unresolved source are left out of every count and grouping of each view
    that holds the source; the view lists it instead.
    """

    misfiled, unusable = tuple(misfiled), tuple(unusable)
    subsections, unresolved = tuple(subsections), tuple(unresolved)
    findings = (misfiled, unusable, subsections, unresolved)
    combined = merge(baseline, older)
    _check_findings(combined, *findings)
    reports: dict[str, dict] = {}
    counted: dict[str, corpus.Corpus] = {}
    for name, view in (("baseline", baseline), ("older", older), ("combined", combined)):
        reports[name], counted[name] = _view(view, reference, *findings)
    return {
        "rules": RULES,
        "note": SOURCE_NOTE,
        "views": reports,
        "eligibility_changes": {
            name: eligibility_changes(
                counted[name],
                counted["combined"],
                reports[name]["primary"],
                reports["combined"]["primary"],
            )
            for name in ("baseline", "older")
        },
        "unresolved": [{"source_id": u.source_id, "reason": u.reason} for u in unresolved],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_reference(reference: corpus.Corpus, record: Path) -> dict:
    """Refuse a 2026 rebuild that differs from its frozen record; summarise the match."""

    recorded = [
        (p["passage_id"], p["text_sha256"])
        for p in json.loads(record.read_text(encoding="utf-8"))["passages"]
    ]
    rebuilt = [(p.passage_id, p.text_sha256) for p in reference.passages]
    if recorded != rebuilt:
        raise SystemExit(
            f"refused: the 2026 rebuild differs from the frozen record {record.name} "
            f"({len(rebuilt)} passages rebuilt, {len(recorded)} recorded)"
        )
    return {
        "passages": len(reference.passages),
        "matches_record": True,
        "editions": [d.edition for d in reference.documents],
    }


def run(  # noqa: PLR0913 - the two manifests, the frozen record and the tokenizer
    older_manifest: Path,
    reference_manifest: Path,
    record: Path,
    count_tokens: Callable[[str], int],
    model_limit: int,
    pdftotext: str = "pdftotext",
    *,
    misfiled: Iterable[Misfiled] = MISFILED,
    unusable: Iterable[Unusable] = UNUSABLE,
) -> dict:
    """Build both corpora, check the 2026 rebuild against its frozen record, then report."""

    def build(manifest: Path) -> corpus.Corpus:
        return corpus.build_corpus(
            manifest,
            count_passage_tokens=count_tokens,
            token_budget=TOKEN_BUDGET,
            model_limit=model_limit,
            pdftotext=pdftotext,
        )

    older = build(older_manifest)
    reference = build(reference_manifest)
    checked = _check_reference(reference, record)
    out = report(older, reference, misfiled=misfiled, unusable=unusable)
    out["reference"] = checked
    out["inputs"] = {
        "manifest": {
            "path": _relative(older_manifest),
            "sha256": _sha256(older_manifest),
        },
        "reference_manifest": {
            "path": _relative(reference_manifest),
            "sha256": _sha256(reference_manifest),
        },
        "frozen_record": {"path": _relative(record), "sha256": _sha256(record)},
        "token_budget": TOKEN_BUDGET,
        "model_limit": model_limit,
    }
    return out


def run_views(  # noqa: PLR0913 - the three manifests, the frozen record and the tokenizer
    older_manifest: Path,
    commentaries_manifest: Path,
    reference_manifest: Path,
    record: Path,
    count_tokens: Callable[[str], int],
    model_limit: int,
    pdftotext: str = "pdftotext",
    *,
    misfiled: Iterable[Misfiled] = MISFILED,
    unusable: Iterable[Unusable] = UNUSABLE,
    subsections: Iterable[Subsection] = SUBSECTIONS,
    unresolved: Iterable[Unresolved] = UNRESOLVED,
) -> dict:
    """Build the baseline, the older commentaries and the 2026 reference, check the reference
    against its frozen record as :func:`run` does, then report the three :func:`views`."""

    settings = {
        "count_passage_tokens": count_tokens,
        "token_budget": TOKEN_BUDGET,
        "model_limit": model_limit,
        "pdftotext": pdftotext,
    }
    baseline = corpus.build_corpus(older_manifest, **settings)
    older = corpus.build_commentaries(commentaries_manifest, **settings)
    reference = corpus.build_corpus(reference_manifest, **settings)
    checked = _check_reference(reference, record)
    out = views(
        baseline,
        older,
        reference,
        misfiled=misfiled,
        unusable=unusable,
        subsections=subsections,
        unresolved=unresolved,
    )
    out["reference"] = checked
    out["inputs"] = {
        "manifest": _file(older_manifest),
        "older_commentaries_manifest": _file(commentaries_manifest),
        "reference_manifest": _file(reference_manifest),
        "frozen_record": _file(record),
        "token_budget": TOKEN_BUDGET,
        "model_limit": model_limit,
    }
    return out


def _file(path: Path) -> dict:
    return {"path": _relative(path), "sha256": _sha256(path)}


def _relative(path: Path) -> str:
    resolved = path.resolve()
    return (
        resolved.relative_to(REPO).as_posix()
        if resolved.is_relative_to(REPO)
        else path.name
    )


def _e5_model():
    """The e5 model behind the passage-token counter, from the local Hugging Face cache only.

    Offline mode is forced before ``huggingface_hub`` is imported here and checked to hold, so a
    missing model is refused, never downloaded; so is the 16-dimensional stub fallback.
    """

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        from huggingface_hub import constants  # noqa: PLC0415
        import run_eval  # noqa: PLC0415 - the pilot's e5 loader and exact token counter
    except ImportError as exc:
        raise SystemExit(
            f"refused: {exc.name} is not installed; run with the ingestion ai extra"
        )
    if not constants.HF_HUB_OFFLINE:  # imported earlier, before offline mode was set
        raise SystemExit(
            "refused: Hugging Face offline mode is not in effect; set HF_HUB_OFFLINE=1 so that "
            "no model can be downloaded"
        )
    try:
        _, model = run_eval._e5()  # refuses the stub fallback
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - a model file or package missing, however it fails
        raise SystemExit(
            f"refused: the cached e5 model could not be loaded ({type(exc).__name__}: {exc}); "
            "nothing is downloaded"
        ) from None
    return run_eval, model


def main(argv: list[str] | None = None) -> int:
    """Run the inventory with the e5 tokenizer and write a new record (no text, no model call)."""

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out", type=Path, required=True, help="the new JSON record to write"
    )
    parser.add_argument(
        "--older-commentaries",
        type=Path,
        help="a commentary-source manifest: the record then holds the baseline, older and "
        "combined views",
    )
    args = parser.parse_args(argv)
    if args.out.exists():  # recorded inventories are evidence, never replaced
        raise SystemExit(
            f"refused: {args.out} already exists; write a new record instead"
        )
    run_eval, model = _e5_model()
    if args.older_commentaries is None:
        out = run(
            OLDER,
            REFERENCE,
            RECORD,
            run_eval._counter(model, "passage"),
            model.max_seq_length,
        )
    else:
        out = run_views(
            OLDER,
            args.older_commentaries,
            REFERENCE,
            RECORD,
            run_eval._counter(model, "passage"),
            model.max_seq_length,
        )
    environment = run_eval._environment(model)
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "tools/commentary_rag",
            "data/manifests",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    out["environment"] = {
        "python": environment["python"],
        "pdftotext": environment["pdftotext"],
        "packages": environment["packages"],
        "model": {
            k: environment["model"][k]
            for k in ("id", "cache_revision", "max_seq_length")
        },
        "git_head": environment["git_head"],
        "tool_files_uncommitted": bool(status),
        "tool_files_sha256": {
            name: _sha256(HERE / name)
            for name in ("training_inventory.py", "corpus.py")
        },
    }
    with open(
        args.out, "x", encoding="utf-8"
    ) as handle:  # never replaces an existing file
        handle.write(
            json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        )
    if args.older_commentaries is not None:
        for name, view in out["views"].items():
            overall = view["primary"]["counts"]["overall"]
            print(
                f"{name}: eligible {overall['eligible_passages']} passages in "
                f"{overall['eligible_families']} families "
                f"(threshold met: {view['primary']['threshold']['met']})"
            )
        print(f"wrote {args.out}")
        return 0
    overall = out["primary"]["counts"]["overall"]
    print(
        f"eligible: {overall['eligible_passages']} passages in {overall['eligible_families']} "
        f"families (threshold met: {out['primary']['threshold']['met']}); wrote {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
