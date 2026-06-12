#!/usr/bin/env python3
"""cas_check — deterministic fitness functions for the CAS grading anchors. Stdlib only.

Measures the STRUCTURAL FLOOR of all 18 criteria: the anchor elements that can be
verified mechanically (files, sections, table columns, counted patterns), each with an
evidence pointer. It never estimates points — quality judgment belongs to the
grade-auditor (/cas-audit). Anchor source: docs/cas/bewertungskriterien-anker.md
(git-ignored local copy of the official Bewertungskriterien, 12 Jun 2026).

Scoring there is CONJUNCTIVE — one missing element drops a whole level — which is why
this tool's ratchet exists: an element that ever passed must keep passing.

Usage:
  python3 tools/cas_check.py            # human table
  python3 tools/cas_check.py --json     # machine output (board, CI artifact)
  python3 tools/cas_check.py --ci       # read-only; exit 1 ONLY on ratchet regressions

Baseline: tools/cas_baseline.json (committed — CI compares against it; local runs extend it).
"""
import datetime
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(os.environ.get("CAS_ROOT") or pathlib.Path(__file__).resolve().parents[1])
BASELINE = ROOT / "tools" / "cas_baseline.json"
ARC = ROOT / "docs" / "arc42"
MET = ROOT / "docs" / "method"
DIA = ROOT / "docs" / "diagrams"

WEIGHTS = {1: 5, 2: 5, 3: 5, 4: 7, 5: 7, 6: 3, 7: 7, 8: 10, 9: 3, 10: 2,
           11: 5, 12: 5, 13: 3, 14: 3, 15: 12, 16: 6, 17: 5, 18: 7}
NAMES = {1: "Use-Cases & Anforderungen", 2: "NfA nach SMART", 3: "Vision",
         4: "Architektur bild+text", 5: "Perspektiven", 6: "Datenmodell",
         7: "Code-Struktur", 8: "Framework-Konzepte", 9: "Erkenntnisse",
         10: "Git-Repository", 11: "Abnahmekriterien", 12: "Teststrategie",
         13: "Unit-Tests", 14: "Test-Ergebnisse", 15: "KI-Werkzeuge",
         16: "KI-Services", 17: "Container-Sub-Systeme", 18: "Fazit"}

# Block ends (Block 0..3); elements due in a later block report as "due", not "miss".
BLOCK_END = {0: datetime.date(2026, 6, 14), 1: datetime.date(2026, 6, 21),
             2: datetime.date(2026, 6, 28), 3: datetime.date(2026, 7, 5)}

def cur_block(today=None):
    t = today or datetime.date.today()
    for b in (0, 1, 2):
        if t <= BLOCK_END[b]:
            return b
    return 3

# ---------------- primitives ----------------

_RD = {}

def rd(p):
    p = pathlib.Path(p)
    k = str(p)
    if k not in _RD:
        try:
            _RD[k] = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            _RD[k] = ""
    return _RD[k]

def cnt(p, pat):
    return len(re.findall(pat, rd(p), re.I | re.M))

def has(p, pat):
    return cnt(p, pat) > 0

def has_any(paths, pat):
    return any(has(p, pat) for p in paths)

def glob1(pat):
    return next(iter(ROOT.glob(pat)), None)

def nglob(pat):
    return len(list(ROOT.glob(pat)))

def arc_corpus():
    return "\n".join(rd(p) for p in sorted(ARC.glob("*.md")))

def walk_tests():
    names = []
    for base in (ROOT / "services",):
        for p in base.rglob("test_*.py"):
            if any(x in p.parts for x in (".venv", "node_modules", "__pycache__")):
                continue
            names += re.findall(r"def (test_[a-z0-9_]+)", rd(p))
    return names

# ---------------- the elements (id, crit, label, due_block, fn) ----------------

def ELEMENTS():
    A01, A10, A13 = ARC / "01-introduction-goals.md", ARC / "10-quality-requirements.md", ARC / "13-test-strategy.md"
    L = ROOT / "LEARNINGS.md"
    AIT, FAZ = MET / "ai-tools.md", MET / "fazit.md"
    corpus = arc_corpus()
    tests = walk_tests()
    E = []
    a = E.append
    # 1 — Use-Cases
    a(("1.catalogue", 1, "UC-Katalog vorhanden (UC-xx)", 0, lambda: has(A01, r"UC-0\d"), str(A01)))
    a(("1.kern", 1, "Kernfunktionen markiert (3–5)", 0, lambda: has(A01, r"Kernfunktion"), str(A01)))
    a(("1.stakeholder", 1, "Stakeholder-Tabelle", 0, lambda: has(A01, r"Stakeholder"), str(A01)))
    a(("1.diagram", 1, "Use-Case-Diagramm", 0, lambda: (DIA / "use-cases.svg").exists(), str(DIA / "use-cases.svg")))
    # 2 — NfA
    a(("2.zielwert", 2, "NfA mit Zielwerten", 0, lambda: has(A10, r"Zielwert"), str(A10)))
    a(("2.messverfahren", 2, "Messverfahren-Spalte", 0, lambda: has(A10, r"Messverfahren"), str(A10)))
    a(("2.adr", 2, "ADR-Bezug (≥3 Refs)", 0, lambda: cnt(A10, r"ADR-\d") >= 3, str(A10)))
    a(("2.count", 2, "≥3 NfA", 0, lambda: cnt(A10, r"NfA-?\d") >= 3, str(A10)))
    # 3 — Vision
    a(("3.problem", 3, "Problemstellung", 0, lambda: has(A01, r"Problemstellung|problem statement"), str(A01)))
    a(("3.vision", 3, "Vision mit Zielgruppe/Abgrenzung", 0, lambda: has(A01, r"Vision"), str(A01)))
    a(("3.kinutzen", 3, "KI-Nutzen je Kernfunktion", 0, lambda: has(A01, r"KI-Nutzen"), str(A01)))
    # 4 — Architektur
    a(("4.c4l1", 4, "C4 Kontext (L1)", 0, lambda: (DIA / "c4-context.svg").exists(), str(DIA / "c4-context.svg")))
    a(("4.c4l2", 4, "C4 Container (L2)", 0, lambda: (DIA / "c4-container.svg").exists(), str(DIA / "c4-container.svg")))
    a(("4.styleadr", 4, "Architekturstil per ADR", 0, lambda: glob1("docs/adr/002-*.md") is not None, "docs/adr/002-*"))
    a(("4.adrs", 4, "ADRs für wichtigste Entscheidungen (≥10)", 0, lambda: nglob("docs/adr/0*.md") >= 10, "docs/adr/"))
    # 5 — Perspektiven
    a(("5.struktur", 5, "Struktur: Komponenten-Diagramm", 0, lambda: nglob("docs/diagrams/c4-component-*.svg") >= 1, "docs/diagrams/c4-component-*"))
    a(("5.verhalten", 5, "Verhalten: Sequenz/Runtime", 0, lambda: nglob("docs/diagrams/seq-*.svg") + nglob("docs/diagrams/runtime-*.svg") >= 2, "docs/diagrams/seq-*,runtime-*"))
    a(("5.zustand", 5, "Zustandsdiagramm", 0, lambda: nglob("docs/diagrams/state-*.svg") >= 1, "docs/diagrams/state-*"))
    a(("5.interaktion", 5, "Interaktion: OpenAPI dokumentiert", 0, lambda: "OpenAPI" in corpus, "docs/arc42/"))
    # 6 — Datenmodell
    a(("6.er", 6, "ER-Diagramm", 0, lambda: nglob("docs/diagrams/er-*.svg") >= 1, "docs/diagrams/er-*"))
    a(("6.migrations", 6, "Migrations-Skripte", 0, lambda: nglob("db/migrations/*") >= 1, "db/migrations/"))
    a(("6.vector", 6, "Vektor-DB dokumentiert", 0, lambda: "pgvector" in corpus, "docs/arc42/"))
    # 7 — Code-Struktur
    a(("7.services", 7, "Service-Grenzen (ingestion/serving/mcp)", 0, lambda: all((ROOT / "services" / s).is_dir() for s in ("ingestion", "serving", "mcp")), "services/"))
    a(("7.readmes", 7, "READMEs je Service (≥3)", 0, lambda: nglob("services/*/README.md") >= 3, "services/*/README.md"))
    a(("7.appsplit", 7, "Console als eigenes App-Modul", 0, lambda: (ROOT / "apps" / "tarifguard").is_dir(), "apps/tarifguard"))
    # 8 — Framework
    a(("8.page", 8, "§8-Seite vorhanden", 0, lambda: (ARC / "08-crosscutting-concepts.md").exists(), str(ARC / "08-crosscutting-concepts.md")))
    a(("8.quote", 8, "Kriterium 8 wörtlich zitiert", 0, lambda: has(ARC / "08-crosscutting-concepts.md", r"gewählten Frameworks"), "arc42/08"))
    a(("8.concepts", 8, "DI + Konfiguration + Fehlerbehandlung benannt", 0,
       lambda: has(ARC / "08-crosscutting-concepts.md", r"Depends|Dependency Injection")
       and has(ARC / "08-crosscutting-concepts.md", r"Konfiguration|configuration")
       and has(ARC / "08-crosscutting-concepts.md", r"Fehlerbehandlung|error handling"), "arc42/08"))
    a(("8.justify", 8, "Framework-Wahl begründet (ADR-001 im Bericht)", 0, lambda: has_any([ARC / "04-solution-strategy.md", ARC / "08-crosscutting-concepts.md"], r"ADR-001"), "arc42/04+08"))
    # 9 — Erkenntnisse
    a(("9.file", 9, "LEARNINGS.md vorhanden", 0, lambda: L.exists(), str(L)))
    a(("9.entries", 9, "≥8 Einträge", 0, lambda: cnt(L, r"^- \*\*20\d\d") >= 8, str(L)))
    a(("9.refs", 9, "Commit-Referenzen je Eintrag", 0, lambda: cnt(L, r"PR #\d+, [0-9a-f]{7}") >= 8, str(L)))
    a(("9.dispositions", 9, "Dispositionen ✓/±/✗ vorhanden", 0, lambda: all(s in rd(L) for s in ("✓", "±", "✗")), str(L)))
    # 10 — Git-Repo (public + URL = pre-flight)
    a(("10.url", 10, "Repo-URL im Bericht", 3, lambda: has_any([ROOT / "docs" / "index.md", ROOT / "README.md"], r"github\.com/\S+/tarifhub"), "docs/index.md"))
    # 11 — Abnahmekriterien
    a(("11.gwt", 11, "G/W/T je Kernfunktion (≥5)", 1, lambda: cnt(A10, r"\bGiven\b") >= 5, str(A10)))
    a(("11.nfaref", 11, "NfA-Querverweise (≥5)", 1, lambda: cnt(A10, r"NfA-?\d") >= 5 and has(A10, r"Verif\w*"), str(A10)))
    # 12 — Teststrategie
    a(("12.doc", 12, "Strategie-Dokument (§13)", 1, lambda: A13.exists(), str(A13)))
    a(("12.levels", 12, "Teststufen benannt+begründet", 1, lambda: has(A13, r"Unit") and has(A13, r"Integration"), str(A13)))
    a(("12.ai", 12, "„Tests der KI-Anteile“-Abschnitt", 1, lambda: has(A13, r"Tests der KI-Anteile"), str(A13)))
    a(("12.named", 12, "Zitierte Testnamen existieren (≥6)", 1, lambda: len(set(re.findall(r"test_[a-z0-9_]+", rd(A13))) & set(tests)) >= 6, str(A13)))
    # 13 — Unit-Tests
    a(("13.count", 13, "Kernlogik abgedeckt (≥100 Tests)", 0, lambda: len(tests) >= 100, "services/**/test_*.py"))
    a(("13.errors", 13, "Fehlerfälle getestet (≥8)", 0, lambda: sum(1 for t in tests if re.search(r"error|fail|invalid|lossy|reject|missing", t)) >= 8, "services/**/test_*.py"))
    a(("13.build", 13, "Tests laufen im Build", 0, lambda: has(ROOT / ".github" / "workflows" / "ci.yml", r"pytest"), ".github/workflows/ci.yml"))
    # 14 — Test-Ergebnisse (due Block 2)
    a(("14.output", 14, "Pipeline-Ausgabe zitiert", 2, lambda: has(A10, r"\d+ passed"), str(A10)))
    a(("14.interpret", 14, "Ergebnisse interpretiert", 2, lambda: has(A10, r"[Ii]nterpret"), str(A10)))
    a(("14.coverage", 14, "Coverage-Zahlen", 2, lambda: has(A10, r"\d{2}\s?%"), str(A10)))
    # 15 — KI-Werkzeuge (due Block 3)
    a(("15.chapter", 15, "KI-Kapitel vorhanden", 3, lambda: AIT.exists() and len(rd(AIT)) > 2000, str(AIT)))
    a(("15.phases", 15, "Phasenstruktur (Generierung/Review/Refactoring/Recherche)", 3, lambda: all(has(AIT, w) for w in ("Generierung", "Review", "Refactoring", "Recherche")), str(AIT)))
    a(("15.evidence", 15, "Belege: Prompts/Diffs/Commits (≥6)", 3, lambda: cnt(AIT, r"[0-9a-f]{7}|PR #\d+") >= 6, str(AIT)))
    a(("15.erklaerung", 15, "Erklärung der Eigenständigkeit", 3, lambda: has(AIT, r"Eigenständigkeit"), str(AIT)))
    # 16 — KI-Services
    a(("16.roles", 16, "≥2 KI-Rollen dokumentiert (ai_map · Suche · MCP)", 1, lambda: ("ai_map" in corpus) and (re.search(r"pgvector|Embedding", corpus, re.I) is not None) and ("MCP" in corpus), "docs/arc42/"))
    a(("16.guardrails", 16, "Guardrails dokumentiert", 1, lambda: re.search(r"guardrail|freeze|gap-gate", corpus, re.I) is not None, "docs/arc42/"))
    a(("16.hitl", 16, "Human-in-the-Loop dokumentiert", 1, lambda: re.search(r"Human-in-the-Loop|Review-?Queue|review queue", corpus, re.I) is not None, "docs/arc42/"))
    # 17 — Container (captures due Block 2)
    a(("17.compose", 17, "Compose vorhanden", 0, lambda: (ROOT / "deploy" / "docker-compose.yml").exists(), "deploy/docker-compose.yml"))
    a(("17.dockerfiles", 17, "Dockerfiles je Sub-System (≥4)", 0, lambda: nglob("services/*/Dockerfile") + nglob("apps/*/Dockerfile") >= 4, "services/,apps/"))
    a(("17.helm", 17, "Helm-Chart", 0, lambda: nglob("deploy/helm/*/Chart.yaml") >= 1, "deploy/helm/"))
    a(("17.justify", 17, "Stilwahl begründet (ADR-002/006 im Bericht)", 0, lambda: re.search(r"ADR-00[26]", rd(ARC / "04-solution-strategy.md") + rd(ARC / "07-deployment-view.md")) is not None, "arc42/04+07"))
    a(("17.captures", 17, "Betriebs-Evidenz erfasst (docs/img)", 2, lambda: nglob("docs/img/**/*") >= 1 and any(p.is_file() for p in ROOT.glob("docs/img/**/*")), "docs/img/"))
    # 18 — Fazit (due Block 3)
    a(("18.chapter", 18, "Fazit-Kapitel substanziell", 3, lambda: FAZ.exists() and len(rd(FAZ)) > 2500, str(FAZ)))
    a(("18.vetoes", 18, "3 Veto-Entscheidungen", 3, lambda: cnt(FAZ, r"[Vv]eto") >= 3, str(FAZ)))
    a(("18.transfer", 18, "Übertrag auf künftige Arbeitsweise", 3, lambda: has(FAZ, r"Übertrag|künftig"), str(FAZ)))
    a(("18.material", 18, "Fazit-Rohmaterial wächst (≥5 Notizen)", 1, lambda: cnt(ROOT / "vault" / "fazit-notes.md", r"^- ") >= 5, "vault/fazit-notes.md"))
    return E

# ---------------- run ----------------

def run(today=None):
    block = cur_block(today)
    rows = []
    for eid, crit, label, due, fn, ev in ELEMENTS():
        try:
            ok = bool(fn())
        except Exception:
            ok = False
        status = "pass" if ok else ("due" if due > block else "miss")
        rows.append({"id": eid, "crit": crit, "label": label, "due": due,
                     "status": status, "evidence": ev})
    base = set()
    if BASELINE.exists():
        try:
            base = set(json.loads(BASELINE.read_text()).get("passed", []))
        except Exception:
            base = set()
    passed_now = {r["id"] for r in rows if r["status"] == "pass"}
    regressions = sorted(base - passed_now)
    for r in rows:
        if r["id"] in regressions:
            r["status"] = "regression"
    crits = []
    for c in range(1, 19):
        es = [r for r in rows if r["crit"] == c]
        crits.append({"c": c, "w": WEIGHTS[c], "name": NAMES[c],
                      "passed": sum(1 for r in es if r["status"] == "pass"),
                      "applicable": sum(1 for r in es if r["status"] in ("pass", "miss", "regression")),
                      "due": sum(1 for r in es if r["status"] == "due"),
                      "elements": es})
    data = {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "block": block,
            "criteria": crits,
            "totals": {"passed": len(passed_now),
                       "applicable": sum(1 for r in rows if r["status"] in ("pass", "miss", "regression")),
                       "due": sum(1 for r in rows if r["status"] == "due"),
                       "elements": len(rows)},
            "regressions": regressions}
    return data, base, passed_now

def main():
    ci = "--ci" in sys.argv
    data, base, passed_now = run()
    if not ci:
        try:
            merged = sorted(base | passed_now)
            if merged != sorted(base):     # write only on real change — no timestamp churn
                BASELINE.write_text(json.dumps({"passed": merged,
                                                "updated": data["generated"]}, indent=1) + "\n")
        except Exception:
            pass
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=1))
    else:
        t = data["totals"]
        print(f"CAS structural floor · Block {data['block']} · "
              f"{t['passed']}/{t['applicable']} elements present · {t['due']} not yet due"
              + (f" · REGRESSIONS: {len(data['regressions'])}" if data["regressions"] else ""))
        print("-" * 78)
        mark = {"pass": "✅", "miss": "⛔", "due": "🕓", "regression": "🔻"}
        for c in data["criteria"]:
            bar = "".join("■" if e["status"] == "pass" else ("·" if e["status"] == "due" else "□")
                          for e in c["elements"])
            print(f"{c['c']:>2} ({c['w']:>2}) {c['name']:<28} {bar}  {c['passed']}/{c['applicable']}"
                  + (f"  (+{c['due']} due)" if c["due"] else ""))
            for e in c["elements"]:
                if e["status"] in ("miss", "regression"):
                    print(f"        {mark[e['status']]} {e['label']}  → {e['evidence']}")
        if data["regressions"]:
            print(f"\n🔻 RATCHET REGRESSIONS (once passed, now missing): {', '.join(data['regressions'])}")
    sys.exit(1 if (ci and data["regressions"]) else 0)

if __name__ == "__main__":
    main()
