#!/usr/bin/env python3
"""Assemble the FFHS submission PDF.

Pipeline: per-chapter markdown -> pandoc (gfm -> LaTeX fragment) -> assembled into
the official FFHS thesis class (docs/latex_template/ffhsthesis.cls) -> tectonic.

SVG diagrams are converted to PDF with rsvg-convert; PNG screenshots are embedded
directly. Non-ASCII typographic glyphs (arrows, multiplication sign, ellipsis) are
normalised to ASCII in the *build copy only* so the Type1 Helvetica of the class
renders them; the committed markdown (and the HTML site) keep their original glyphs.
Umlauts are preserved. Em-dashes must already be zero in the source (owner style law);
any residual is normalised here as a belt-and-suspenders measure.

Usage:  python3 tools/build_pdf.py            # build site PDF -> build/pdf/tarifhub-cas.pdf
        python3 tools/build_pdf.py --check    # verify toolchain only
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TEMPLATE = DOCS / "latex_template"
BUILD = ROOT / "build" / "pdf"
IMGDIR = BUILD / "img"
OUT_TEX = BUILD / "tarifhub-cas.tex"
OUT_PDF = BUILD / "tarifhub-cas.pdf"

REPO_URL = "https://github.com/erhanuenlue/tarifhub"

# --- document structure (in order) ----------------------------------------
# Front-matter German summary sits right after the cover (owner spec).
SUMMARY = "zusammenfassung-de.md"

ARC42 = [
    "arc42/01-introduction-goals.md",
    "arc42/02-constraints.md",
    "arc42/03-context-scope.md",
    "arc42/04-solution-strategy.md",
    "arc42/05-building-block-view.md",
    "arc42/06-runtime-view.md",
    "arc42/07-deployment-view.md",
    "arc42/08-crosscutting-concepts.md",
    "arc42/09-architecture-decisions.md",
    "arc42/10-quality-requirements.md",
    "arc42/11-risks-technical-debt.md",
    "arc42/12-glossary.md",
    "arc42/13-test-strategy.md",
]

METHOD = [
    "method/ai-se-framework.md",
    "method/ai-tools.md",
    "method/decision-matrix.md",
    "method/journal.md",
    "method/fazit.md",
]

APPENDIX = ["criterion-map.md"]

# --- typographic normalisation for the Type1 font (build copy only) --------
NORMALIZE = {
    "—": ", ",   # em dash  (should be swept from source already)
    "–": "-",     # en dash
    "→": " to ",  # right arrow
    "←": " from ",# left arrow
    "↔": " <-> ", # left-right arrow
    "↩": "",      # hook-return arrow (vault index footer)
    "×": "x",     # multiplication sign
    "…": "...",   # ellipsis
    "✓": "[ok]",  # check mark
    "✗": "[no]",  # ballot x
    "±": "+/-",   # plus-minus
    "≡": "==",    # identical
    "≠": "!=",    # not equal
    "−": "-",     # U+2212 true minus (penalty values like -0.25)
    "∅": "none",  # empty set (gap-before markers in evidence tables)
    "≥": ">=",
    "≤": "<=",
    "“": '"', "”": '"', "„": '"',
    "‘": "'", "’": "'",
    " ": " ",     # non-breaking space
    " ": " ",     # narrow nbsp
    "€": "EUR",
    " ": " ",     # thin space
    "•": "-",     # bullet
    "·": "-",     # U+00B7 middot (arc42 chapter-title separator; misrenders as "ù" under XeTeX+T1 helvet)
    "■": "#", "□": ".",  # cas_check block glyphs (not expected here)
}


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def need(tool: str) -> bool:
    return shutil.which(tool) is not None


def check_toolchain() -> bool:
    ok = True
    for t in ("pandoc", "tectonic", "rsvg-convert"):
        present = need(t)
        print(f"  {t:14} {'OK' if present else 'MISSING'}")
        ok = ok and present
    return ok


def normalize_text(s: str) -> str:
    for a, b in NORMALIZE.items():
        s = s.replace(a, b)
    return s


_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def convert_svg(src: Path) -> Path:
    """Convert an SVG to PDF (cached in build/img) and return the PDF path."""
    IMGDIR.mkdir(parents=True, exist_ok=True)
    out = IMGDIR / (src.stem + ".pdf")
    if not out.exists():
        r = sh(["rsvg-convert", "-f", "pdf", "-o", str(out), str(src)])
        if r.returncode != 0:
            print(f"  ! svg->pdf failed for {src.name}: {r.stderr.strip()}", file=sys.stderr)
            return src
    return out


def rewrite_images(md_text: str, md_path: Path) -> str:
    base = md_path.parent

    def repl(m: re.Match) -> str:
        alt, ref = m.group(1), m.group(2)
        target = (base / ref).resolve()
        if not target.exists():
            print(f"  ! image not found: {ref} (in {md_path.name})", file=sys.stderr)
            return ""  # drop missing image rather than break the build
        if target.suffix.lower() == ".svg":
            target = convert_svg(target)
        return f"![{alt}]({target.as_posix()})"

    return _IMG_RE.sub(repl, md_text)


def md_to_fragment(rel: str, *, top_level: str = "chapter") -> str:
    md_path = DOCS / rel
    if not md_path.exists():
        print(f"  ! chapter missing, skipped: {rel}", file=sys.stderr)
        return f"\\par\\textit{{[missing source: {rel}]}}\\par\n"
    text = md_path.read_text(encoding="utf-8")
    text = rewrite_images(text, md_path)
    text = normalize_text(text)
    tmp = BUILD / "_frag_src.md"
    tmp.write_text(text, encoding="utf-8")
    r = sh([
        "pandoc", "-f", "gfm", "-t", "latex",
        f"--top-level-division={top_level}",
        "--syntax-highlighting=none",
        "--wrap=preserve",
        str(tmp),
    ])
    if r.returncode != 0:
        print(f"  ! pandoc failed on {rel}: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    frag = r.stdout
    # bound every image to the text block so wide diagrams/screenshots never overflow
    frag = frag.replace(
        "\\includegraphics{",
        "\\includegraphics[width=\\linewidth,height=0.42\\textheight,keepaspectratio]{",
    )
    frag = re.sub(
        r"\\includegraphics\[([^\]]*)\]\{",
        lambda m: ("\\includegraphics[width=\\linewidth,height=0.42\\textheight,keepaspectratio]{"
                   if "width" not in m.group(1) else m.group(0)),
        frag,
    )
    # pandoc emits naked l/c/r column specs from GFM, so wide tables overflow the margin.
    # Rewrite every table to equal-width wrapping p-columns bounded to the line width.
    def _wrap_cols(m: re.Match) -> str:
        n = len(m.group(1))
        col = (">{\\raggedright\\arraybackslash}p{\\dimexpr(\\linewidth - "
               + str(2 * n) + "\\tabcolsep)/" + str(n) + "\\relax}")
        return "\\begin{longtable}[]{@{}" + col * n + "@{}}"
    frag = re.sub(r"\\begin\{longtable\}\[\]\{@\{\}([lrc]+)@\{\}\}", _wrap_cols, frag)
    # shrink font + padding so dense tables stay readable within the margin
    frag = frag.replace("\\begin{longtable}", "\\begingroup\\footnotesize\\setlength{\\tabcolsep}{3pt}\\begin{longtable}")
    frag = frag.replace("\\end{longtable}", "\\end{longtable}\\endgroup")
    # Allow long inline literals (paths, hashes, dotted ids) to break at separators.
    # Done here in pure text (insert \allowbreak after / . _), so there is no LaTeX-side
    # token rescanning (that is what made the seqsplit approach loop). Hang-free.
    frag = re.sub(
        r"\\texttt\{([^{}]*)\}",
        lambda m: "\\texttt{" + re.sub(r"([/._])", r"\1\\allowbreak{}", m.group(1)) + "}",
        frag,
    )
    # also let slash-joined separate code spans break between them
    frag = frag.replace("}/\\texttt{", "}/\\allowbreak\\texttt{")
    # break after escaped close-brace and after > so URL templates ({system}/{code}?as_of=<date>) wrap
    frag = frag.replace("\\}", "\\}\\allowbreak{}")
    frag = frag.replace("\\textgreater{}", "\\textgreater{}\\allowbreak{}")
    # code blocks: pandoc emits plain verbatim (no wrapping); use fvextra Verbatim so long
    # lines (64-char hashes, JSON) break instead of running off the page. Hang-free.
    frag = frag.replace(
        "\\begin{verbatim}",
        "\\begin{Verbatim}[breaklines=true,breakanywhere=true,fontsize=\\footnotesize]",
    )
    frag = frag.replace("\\end{verbatim}", "\\end{Verbatim}")
    return frag


PREAMBLE = r"""
\usepackage{longtable,booktabs,array,calc}
\usepackage{multirow}
\usepackage[normalem]{ulem}
\usepackage{xcolor}
\usepackage{fvextra}
\usepackage{textcomp}
\usepackage[hidelinks]{hyperref}
\hypersetup{breaklinks=true}
\usepackage{xurl}
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\passthrough}[1]{#1}
\providecommand{\pandocbounded}[1]{#1}
\setlength{\emergencystretch}{3em}
\sloppy
"""


def front_matter() -> str:
    return r"""\documentclass{ffhsthesis}
""" + PREAMBLE + r"""
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.6em}

\dokumentTyp{Projektarbeit CAS AISE}
\studiengang{CAS AI-Assisted Software Engineering}
\title{TarifHub}
\subtitle{KI-gestützte Harmonisierung über einer deterministischen Freeze-Line\\[0.4ex]\normalsize\href{""" + REPO_URL + r"""}{""" + REPO_URL.replace("https://", "") + r"""}}
\author{Erhan Ünlü}
\wohnort{Schweiz, 2026}
\referent{FFHS\\ Departement Informatik\\ CAS AISE}
\eingereichtBei{Fernfachhochschule Schweiz\\ CAS AI-Assisted Software Engineering\\ Gruppe K}

\begin{document}
\maketitle

\pagenumbering{roman}
\chapter*{Zusammenfassung (Deutsch)}
\addcontentsline{toc}{chapter}{Zusammenfassung (Deutsch)}
\noindent Repository: \href{""" + REPO_URL + r"""}{""" + REPO_URL + r"""}
\par\medskip
""" + "%%SUMMARY%%" + r"""

\newpage
\tableofcontents

\startThesis
"""


HILFSMITTEL = r"""
\newpage
\chapter*{Hilfsmittelverzeichnis}
\addcontentsline{toc}{chapter}{Hilfsmittelverzeichnis}
\noindent Die KI-gestützte Arbeitsweise ist vollständig im Kapitel \emph{AI Tools and Workflow} (Kriterium 15) dokumentiert und durch Prompts, Diffs und Commit-Referenzen belegt. Übersicht der eingesetzten Hilfsmittel:
\par\medskip
{\footnotesize\setlength{\tabcolsep}{4pt}
\begin{longtable}{|p{4.4cm}|p{6.2cm}|p{3.2cm}|}
\hline
\textbf{Welches Hilfsmittel?} & \textbf{Wozu eingesetzt?} & \textbf{Betroffene Stellen}\\ \hline
Claude Code (Opus 4.8; Fable 5 in den frühen Blöcken) & Orchestrierung, Generierung, Review, Refactoring (implementer, verifier, determinism-auditor, security-reviewer) & Gesamter Code, gesamte Dokumentation \\ \hline
OpenAI Codex (gpt-5.5) & Unabhängiges Zweitmodell: Review jeder PR; Kuratierung des Journals und der Fazit-Notizen (tools/curate.sh) & Reviews, vault/daily, vault/fazit-notes \\ \hline
guard\_frozen / Hooks (CI, vault, graphify) & Governance der KI durch eigene Werkzeuge: Schutz der Freeze-Line, Journal-Commit, Anker-Ratchet & Freeze-Line, vault/, .github/workflows \\ \hline
Context7, Explore-Agenten & Recherche: aktuelle Bibliotheks-Dokumentation, FHIR-IG-Analyse & Recherche-Phase \\ \hline
\end{longtable}}
"""


ERKLAERUNG = r"""
\newpage
\chapter*{Selbstständigkeitserklärung}
\addcontentsline{toc}{chapter}{Selbstständigkeitserklärung}

\noindent\textit{Hinweis: Diese Seite ist als Platzhalter ausgeführt. Den finalen Wortlaut verfasst und unterzeichnet der Autor (Erhan Ünlü) selbst vor der Einreichung; die Delegation dieser Erklärung an die KI ist ausgeschlossen (siehe Fazit, Veto 3).}
\par\medskip

Hiermit erkläre ich,
\begin{itemize}
    \item dass ich die vorliegende Arbeit selbstständig verfasst habe,
    \item dass alle sinngemäss und wörtlich übernommenen Textstellen aus fremden Quellen kenntlich gemacht wurden,
    \item dass alle mit Hilfsmitteln (einschliesslich KI-Werkzeugen) erbrachten Teile der Arbeit präzise deklariert wurden, im Kapitel \emph{AI Tools and Workflow} und im Hilfsmittelverzeichnis,
    \item dass keine anderen als die aufgeführten Hilfsmittel verwendet wurden,
    \item dass das Thema, die Arbeit oder Teile davon nicht bereits Gegenstand eines Leistungsnachweises eines anderen Moduls waren, sofern dies nicht ausdrücklich im Voraus vereinbart wurde,
    \item dass ich mir bewusst bin, dass meine Arbeit elektronisch auf Plagiate und auf Drittautorschaft menschlichen oder technischen Ursprungs überprüft werden kann.
\end{itemize}

\vspace{3.2cm}
\noindent\hrule \ \\[-0.5ex]
(Ort, Datum, Unterschrift)
\clearpage
"""


def appendix_block() -> str:
    parts = [r"\appendix", r"\chapter{Anhang: Kriterienkarte (Criterion Map)}"]
    for rel in APPENDIX:
        # render the criterion map under the appendix chapter as sections
        parts.append(md_to_fragment(rel, top_level="section"))
    return "\n".join(parts)


def build() -> int:
    BUILD.mkdir(parents=True, exist_ok=True)
    IMGDIR.mkdir(parents=True, exist_ok=True)
    # the class + logo must sit next to the .tex for tectonic to find them
    shutil.copy(TEMPLATE / "ffhsthesis.cls", BUILD / "ffhsthesis.cls")
    shutil.copy(TEMPLATE / "FFHS_Logo.jpg", BUILD / "FFHS_Logo.jpg")

    print("Rendering chapters ...")
    summary = md_to_fragment(SUMMARY, top_level="section")
    # strip the leading \section heading from the summary (it has its own chapter*)
    summary = re.sub(r"^\\section\{[^}]*\}\\label\{[^}]*\}\s*", "", summary, count=1)

    body_parts: list[str] = []
    for rel in ARC42 + METHOD:
        print(f"  + {rel}")
        body_parts.append(md_to_fragment(rel, top_level="chapter"))

    doc = front_matter().replace("%%SUMMARY%%", summary)
    doc += "\n\n".join(body_parts)
    doc += "\n" + appendix_block()
    doc += HILFSMITTEL
    doc += ERKLAERUNG
    doc += "\n\\end{document}\n"

    OUT_TEX.write_text(doc, encoding="utf-8")
    print(f"Wrote {OUT_TEX.relative_to(ROOT)} ({len(doc)} chars)")

    print("Compiling with tectonic ...")
    r = sh(["tectonic", "--keep-logs", str(OUT_TEX)], cwd=str(BUILD))
    # tectonic prints warnings to stderr; only a non-zero exit is fatal
    tail = "\n".join(r.stderr.strip().splitlines()[-25:])
    print(tail)
    if r.returncode != 0:
        print(f"\nTECTONIC FAILED (exit {r.returncode}).", file=sys.stderr)
        return r.returncode
    if OUT_PDF.exists():
        size = OUT_PDF.stat().st_size
        print(f"\nOK: {OUT_PDF.relative_to(ROOT)} ({size//1024} KB)")
        return 0
    print("No PDF produced.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check_toolchain() else 1)
    sys.exit(build())
