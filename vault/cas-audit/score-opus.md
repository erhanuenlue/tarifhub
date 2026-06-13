# CAS Grade Estimate, hostile read (Pass A, blind)

Grader: opus-4.8. Date: 2026-06-13. Total: 90 / 100. Implied Swiss band: roughly 5.5.

## Calibration note

This is a blind, hostile estimate: for each criterion I awarded the lowest score the
anchor text defensibly permits under the conjunctive Stufenregel, and I gave no benefit of
the doubt for intent that is not written on the page. The deterministic structural floor
(tools/cas_check.py, 63/63 elements) is taken as given and not re-derived; my job was prose
quality, diagram-to-text consistency, the roter Faden, whether the framework use is
genuinely idiomatic, whether acceptance criteria truly cross-reference the NfAs, whether the
KI-Anteil tests are named and real, and whether the Fazit vetoes are concrete and evidenced.
On the substance the dossier is strong and largely earns full marks: the spec chapters, the
arc42 design, the test strategy (with a real, named Tests-der-KI-Anteile section), the
quoted-and-interpreted pipeline evidence, and a Fazit built on three evidenced vetoes are all
at the vollständig anchor. Three places do not survive a hostile read: the
Eigenständigkeitserklärung is an unsigned placeholder (crit 15), two framework concepts are
admitted as not-yet-wired (crit 8), and the repository is, by the project's own Fazit, still
private at the grading moment (crit 10). I report each at the lower level and name exactly
what would secure the higher one.

## Score table

| # | Kriterium | max | Punkte | Stufe | Belegpfad |
|---|-----------|-----|--------|-------|-----------|
| 1 | Use-Cases und fachliche Anforderungen | 5 | 5 | vollständig | docs/arc42/01-introduction-goals.md#use-case-catalogue |
| 2 | Qualitätsanforderungen (NfA) nach SMART | 5 | 5 | vollständig | docs/arc42/10-quality-requirements.md#quality-goals-smart-nfrs |
| 3 | Vision der Lösung | 5 | 5 | vollständig | docs/arc42/01-introduction-goals.md#vision |
| 4 | Architektur bildlich und textuell | 7 | 7 | vollständig | docs/arc42/05-building-block-view.md |
| 5 | Perspektiven (Struktur, Verhalten, Interaktion) | 7 | 7 | vollständig | docs/arc42/06-runtime-view.md |
| 6 | Datenmodell spezifiziert | 3 | 3 | vollständig | docs/arc42/05-building-block-view.md#data-model |
| 7 | Code-Struktur und Schichten | 7 | 7 | vollständig | services/serving/src/tarifhub_serving/main.py |
| 8 | Framework-Konzepte sachgerecht | 10 | 7 | überwiegend | docs/arc42/08-crosscutting-concepts.md#modern-application-concepts |
| 9 | Erkenntnisse aus der Programmierung | 3 | 3 | vollständig | LEARNINGS.md |
| 10 | Source-Code im Git-Repository | 2 | 0 | nicht | docs/method/fazit.md (Veto 3) |
| 11 | Abnahmekriterien | 5 | 5 | vollständig | docs/arc42/10-quality-requirements.md#acceptance-criteria |
| 12 | Teststrategie inkl. KI-Anteile | 5 | 5 | vollständig | docs/arc42/13-test-strategy.md#tests-der-ki-anteile |
| 13 | Unit-Tests programmiert | 3 | 3 | vollständig | docs/arc42/10-quality-requirements.md#unit-and-contract-tests-offline-suite |
| 14 | Test-Ergebnisse dokumentiert | 3 | 3 | vollständig | docs/arc42/10-quality-requirements.md#test-and-pipeline-results |
| 15 | KI-Werkzeuge beschrieben und belegt | 12 | 7 | überwiegend | docs/method/ai-tools.md#erklarung-der-eigenstandigkeit |
| 16 | Intelligente, flexible KI-Services | 6 | 6 | vollständig | docs/arc42/05-building-block-view.md#level-2-ingestion-service-components |
| 17 | Module/Sub-Systeme als Container lauffähig | 5 | 5 | vollständig | docs/arc42/07-deployment-view.md#style-choice-distributed-services-along-the-freeze-line |
| 18 | Fazit: Reflexion mit drei Vetos | 7 | 7 | vollständig | docs/method/fazit.md |
| | TOTAL | 100 | 90 | | |

## Per-criterion judgment

### 1: Use-Cases und fachliche Anforderungen (5/5)
Anker (vollständig): "Drei bis fünf Kernfunktionen als Use-Cases mit Akteuren und fachlichem Nutzen; Stakeholder identifiziert; Anforderungen eindeutig und widerspruchsfrei."
Beleg: docs/arc42/01-introduction-goals.md#use-case-catalogue
Rationale: Fünf markierte Kernfunktionen mit Akteur, Trigger, Outcome und Nutzen, plus Stakeholder- und FR-Tabelle; Akteure und Nutzen sind bei keiner Funktion lückenhaft, daher greift überwiegend nicht.
- Keine blockierenden Lücken. Hostile-Restzweifel: die gemischten Status-Labels (live / designed / this release) trüben minimal die Lesbarkeit, betreffen aber den Lieferstatus, nicht die Widerspruchsfreiheit der Anforderungen.

### 2: Qualitätsanforderungen nach SMART (5/5)
Anker (vollständig): "Mindestens drei NfA, jede mit messbarem Zielwert und Messverfahren; Bezug zu den Architekturentscheidungen erkennbar (ADR)."
Beleg: docs/arc42/10-quality-requirements.md#quality-goals-smart-nfrs
Rationale: Sechs NfA mit Zielwert, Messverfahren, gemessenem Wert und expliziter ADR-Spalte; der ADR-Bezug ist sichtbar verlinkt, nicht nur erkennbar.
- Keine Lücken.

### 3: Vision (5/5)
Anker (vollständig): "Klare Problemstellung; Vision mit Zielgruppe, realem oder plausiblem Bedürfnis und Abgrenzung; je ein Satz zum KI-Nutzen pro Kernfunktion."
Beleg: docs/arc42/01-introduction-goals.md#vision
Rationale: Problemstellung, Zielgruppe, Bedürfnis und Abgrenzung getrennt benannt; der Abschnitt KI-Nutzen je Kernfunktion liefert genau einen Satz pro Kernfunktion.
- Keine Lücken.

### 4: Architektur bildlich und textuell (7/7)
Anker (vollständig): "C4-Ebenen 1 und 2 vorhanden und konsistent zum Text; Architekturstil benannt und per ADR begründet; ADRs für die wichtigsten Entscheidungen; Bericht mit durchgängigem rotem Faden."
Beleg: docs/arc42/05-building-block-view.md#level-1-containers
Rationale: C4 0/1/2 konsistent zu den Tabellen, Stil per ADR-002 begründet, roter Faden Freeze-Line trägt von §1 bis ins Fazit.
- Keine Lücken.

### 5: Perspektiven (7/7)
Anker (vollständig): "Alle drei Perspektiven abgedeckt (Struktur, Verhalten, Interaktion), jeweils mit Diagramm und erläuterndem Text."
Beleg: docs/arc42/06-runtime-view.md
Rationale: Struktur (C4-Komponenten), Verhalten (drei Sequenzen plus Lifecycle-State), Interaktion (OpenAPI-Verträge plus Use-Case-Diagramm), je mit Diagramm und Text.
- Keine Lücken.

### 6: Datenmodell (3/3)
Anker (vollständig): "Relationales Modell vollständig inkl. Migrations-Skripten; Einsatz der Vektor-Datenbank dokumentiert."
Beleg: docs/arc42/05-building-block-view.md#data-model
Rationale: ER-Modell, db/schema.sql, db/migrations/001_init.sql und die pgvector vector(1024)-Spalte mit HNSW-cosine sind dokumentiert.
- Keine Lücken.

### 7: Code-Struktur (7/7)
Anker (vollständig): "Einheitliche Struktur mit klaren Verantwortlichkeiten; sprechende Namen; Dokumentation an nicht-trivialen Stellen; Modulgrenzen im Code konsistent zum Entwurf."
Beleg: services/serving/src/tarifhub_serving/main.py
Rationale: Saubere Schichten je Service, sprechende Namen, Modul-Docstrings (z. B. Import-Disziplin), Komponententabelle 1:1 zu den Code-Pfaden.
- Keine Lücken.

### 8: Framework-Konzepte (7/10)
Anker (überwiegend, zuerkannt): "Framework-Mittel mehrheitlich idiomatisch eingesetzt; einzelne Umgehungen oder Inkonsistenzen."
Beleg: docs/arc42/08-crosscutting-concepts.md#modern-application-concepts
Rationale: DI, externalisierte Konfiguration, einheitliche Fehlerbehandlung, Validierung idiomatisch belegt und Framework-Wahl per ADR-001 begründet; vollständig scheitert hostil an zwei eingeräumten Inkonsistenzen.
- Observability ist nur per ADR-011 entschieden, nicht instrumentiert.
- TarifGuard-Komponenten- und Playwright-Tests existieren, sind aber nicht an CI verdrahtet (npm run test --if-present ist No-op).
- Was die volle Stufe sichern würde: OpenTelemetry/Sentry instrumentieren und die Konsolen-Tests in den CI-console-Job verdrahten.

### 9: Erkenntnisse aus der Programmierung (3/3)
Anker (vollständig): "Konkrete Erkenntnisse mit Belegen (Diffs oder Commit-Referenzen), insbesondere wo KI-Vorschläge angenommen, korrigiert oder verworfen wurden."
Beleg: LEARNINGS.md
Rationale: Jeder Eintrag trägt PR + Merge-SHA und die Disposition (angenommen/korrigiert/verworfen), z. B. PR #2 057a6c1, PR #7 5da6472.
- Keine Lücken.

### 10: Source-Code im Git-Repository (0/2)
Anker (vollständig, einzige nicht-null Stufe): "Repository-URL im Bericht, Repository zugänglich, Quellcode vollständig."
Beleg: docs/method/fazit.md (Veto 3, PR #17)
Rationale: URL steht im Bericht, aber das Fazit erklärt selbst, dass die Sichtbarkeit erst zum go-live freigeschaltet wird und am 13.06. bewusst privat blieb; ohne Zugänglichkeit zum Bewertungszeitpunkt entfällt die einzige nicht-null Stufe komplett.
- Was die volle Stufe sichert: Repository vor der Abgabe öffentlich schalten (oder dem Bewerter nachweislich Zugang geben), sodass die im Bericht zitierte URL tatsächlich erreichbar ist.

### 11: Abnahmekriterien (5/5)
Anker (vollständig): "Prüfbare Abnahmekriterien pro Kernfunktion, inkl. Bezug zu den Qualitätsanforderungen (Kriterium 2)."
Beleg: docs/arc42/10-quality-requirements.md#acceptance-criteria
Rationale: Given/When/Then je Use-Case gegen ein konkretes Observable, plus eine Spalte "Verifies (NfA)", die jede Zeile explizit auf NfA-1…6 zurückbindet.
- Keine Lücken.

### 12: Teststrategie inkl. KI-Anteile (5/5)
Anker (vollständig): "Teststufen mit Werkzeugen benannt und begründet; Tests der KI-Anteile berücksichtigt (Guardrail-Verhalten, nicht-deterministische Antworten)."
Beleg: docs/arc42/13-test-strategy.md#tests-der-ki-anteile
Rationale: Pyramide begründet benannt; vier KI-Anteil-Testfamilien (Guardrail/Boundary, Gap-Gate no-call, Fill-Reuse-Determinismus, fail-closed Schema) mit echten Testdateinamen.
- Keine Lücken.

### 13: Unit-Tests (3/3)
Anker (vollständig): "Tests decken die Kernlogik ab, inkl. Fehlerfälle; Tests laufen im Build durch."
Beleg: docs/arc42/10-quality-requirements.md#unit-and-contract-tests-offline-suite
Rationale: 295 passed offline, Fehlerfälle konkret benannt, Lauf im CI-python-Job auf jedem Push.
- Keine Lücken.

### 14: Test-Ergebnisse dokumentiert (3/3)
Anker (vollständig): "Ergebnisse nachvollziehbar dokumentiert (Testbericht oder Pipeline-Ausgabe) und im Bericht interpretiert."
Beleg: docs/arc42/10-quality-requirements.md#test-and-pipeline-results
Rationale: Pytest-Summaries, Coverage-Tabellen, der -v-sichtbare Boundary-Output und ein realer Diff-JSON sind wörtlich zitiert und je interpretiert; Screenshots ausdrücklich nur Illustration.
- Keine Lücken. Dies trifft genau den Evidenzstandard, den der Anker für Kriterium 14 verlangt.

### 15: KI-Werkzeuge beschrieben und belegt (7/12)
Anker (überwiegend, zuerkannt): "Einsatz pro Phase beschrieben; Belege nur teilweise; Erklärung der Eigenständigkeit vorhanden."
Beleg: docs/method/ai-tools.md#erklarung-der-eigenstandigkeit
Rationale: Einsatz je Phase (Generierung, Review, Refactoring, Recherche) mit Prompts, Diffs und Commit-Refs stark belegt; vollständig scheitert konjunktiv daran, dass die Erklärung der Eigenständigkeit ein ausdrücklicher, unsignierter Platzhalter ist ("a visible placeholder", "Awaiting the owner's final text and signature").
- Erklärung der Eigenständigkeit ist paraphrasiert und unsigniert, nicht die finale "vollständige" Form.
- Was die volle Stufe sichert: die endgültige, vom Autor selbst verfasste und unterschriebene Erklärung der Eigenständigkeit einsetzen. Erst dann ist der konjunktive Anker erfüllt; die Belegtiefe selbst ist bereits auf vollständig-Niveau.

### 16: Intelligente, flexible KI-Services (6/6)
Anker (vollständig): "Mindestens zwei KI-Rollen substanziell in der Lösung; Guardrails greifen; wo sinnvoll Human-in-the-Loop."
Beleg: docs/arc42/05-building-block-view.md#level-2-ingestion-service-components
Rationale: Zwei substanzielle Rollen (fill-only ai_map plus e5-Embedding-Suche/MCP), Guardrails (Freeze-Line, AST-Boundary, Gap-Gate) greifen, Review-Formular als Human-in-the-Loop.
- Keine Lücken.

### 17: Container lauffähig (5/5)
Anker (vollständig): "Klare Modul- bzw. Service-Grenzen konsistent zum Entwurf; Lösung lauffähig per Compose oder Kubernetes; Wahl des Stils begründet."
Beleg: docs/arc42/07-deployment-view.md#style-choice-distributed-services-along-the-freeze-line
Rationale: Jede Building-Block-Box einem Image zugeordnet, Compose (acht Container, zitiertes docker compose ps) und k3d/Helm lauffähig, verteilter Stil per ADR-002 gegen den gleichwertigen Monolithen begründet.
- Keine Lücken.

### 18: Fazit mit drei Vetos (7/7)
Anker (vollständig): "Reflexionskapitel substanziell: drei Veto-Entscheidungen konkret, begründet und belegt; nachvollziehbarer Übertrag auf die künftige Arbeitsweise."
Beleg: docs/method/fazit.md
Rationale: Drei Vetos je mit konkretem Vorfall und PR/SHA (PR #2, PR #4, PR #17), plus operationalisierbarer Übertrag ("match the working mode to the blast radius").
- Keine Lücken.

## Gap list, ranked by points at risk

1. Crit 15, 5 Punkte: Erklärung der Eigenständigkeit ist unsignierter Platzhalter. Sichern durch finale, signierte Erklärung. Hebt 7 auf 12.
2. Crit 8, 3 Punkte: Observability nicht instrumentiert und Konsolen-Tests nicht in CI verdrahtet. Sichern durch OpenTelemetry/Sentry-Instrumentierung und Verdrahtung der TarifGuard-Tests. Hebt 7 auf 10.
3. Crit 10, 2 Punkte: Repository laut Fazit noch privat. Sichern durch öffentliche Sichtbarkeit (oder Bewerterzugang) vor der Abgabe. Hebt 0 auf 2.

Maximal nachholbar: 10 Punkte, alle drei sind reine Fertigstellungs- bzw. Freischaltungsschritte, keine Substanzlücken.

## Honesty line

This is one model's hostile estimate against the written anchors, not the grader's verdict; the official mark is the lecturer's.
