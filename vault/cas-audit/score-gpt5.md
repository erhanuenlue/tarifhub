# CAS scorecard - gpt-5.5 (blind pass)

Total: 86/100. This is a hostile page-only pass. The dossier earns full marks where the written artifacts quote measurable output and tie claims to code, ADRs and tests. I dropped levels where a conjunctive top anchor is blocked by a visible placeholder, incomplete interaction proof, or uneven veto evidence.

| # | Kriterium | max | Punkte | Stufe | Belegpfad |
|---|---|---:|---:|---|---|
| 1 | Use-Cases und fachliche Anforderungen | 5 | 5 | vollständig bzw. korrekt | docs/arc42/01-introduction-goals.md#use-case-catalogue |
| 2 | Qualitätsanforderungen SMART | 5 | 5 | vollständig bzw. korrekt | docs/arc42/10-quality-requirements.md#quality-goals-smart-nfrs |
| 3 | Vision der Lösung | 5 | 5 | vollständig bzw. korrekt | docs/arc42/01-introduction-goals.md#vision |
| 4 | Lösungsansatz und Architektur | 7 | 4 | überwiegend bzw. mehrheitlich | docs/arc42/05-building-block-view.md#level-0-system-context |
| 5 | Struktur, Verhalten, Interaktion | 7 | 4 | überwiegend bzw. mehrheitlich | docs/arc42/05-building-block-view.md#level-1-containers; docs/arc42/06-runtime-view.md#scenario-1-harmonise-to-freeze |
| 6 | Datenmodell | 3 | 3 | vollständig bzw. korrekt | docs/arc42/05-building-block-view.md#data-model; db/schema.sql |
| 7 | Code-Struktur und Lesbarkeit | 7 | 7 | vollständig bzw. korrekt | docs/arc42/05-building-block-view.md#level-1-containers; services/ |
| 8 | Framework- und Applikationskonzepte | 10 | 10 | vollständig bzw. korrekt | docs/arc42/08-crosscutting-concepts.md#modern-application-concepts |
| 9 | Erkenntnisse aus Programmierung | 3 | 3 | vollständig bzw. korrekt | LEARNINGS.md#learnings |
| 10 | Git-Repository verfügbar | 2 | 2 | vollständig bzw. korrekt | docs/index.md#tarifhub-architecture-documentation |
| 11 | Abnahmekriterien | 5 | 5 | vollständig bzw. korrekt | docs/arc42/10-quality-requirements.md#acceptance-criteria |
| 12 | Teststrategie | 5 | 5 | vollständig bzw. korrekt | docs/arc42/13-test-strategy.md#tests-der-ki-anteile |
| 13 | Unit-Tests programmiert | 3 | 3 | vollständig bzw. korrekt | docs/arc42/10-quality-requirements.md#unit-and-contract-tests-offline-suite; services/*/tests |
| 14 | Test-Ergebnisse dokumentiert | 3 | 3 | vollständig bzw. korrekt | docs/arc42/10-quality-requirements.md#test-and-pipeline-results |
| 15 | KI-Werkzeuge beschrieben | 12 | 7 | überwiegend bzw. mehrheitlich | docs/method/ai-tools.md#generierung; docs/method/ai-tools.md#erklaerung-der-eigenstaendigkeit |
| 16 | Intelligente und flexible KI-Services | 6 | 6 | vollständig bzw. korrekt | docs/arc42/10-quality-requirements.md#harmonisation-results |
| 17 | Module, Sub-Systeme, Container | 5 | 5 | vollständig bzw. korrekt | docs/arc42/07-deployment-view.md#evidence-2-the-full-stack-runs-under-compose |
| 18 | Fazit zu KI-Werkzeugen | 7 | 4 | überwiegend bzw. mehrheitlich | docs/method/fazit.md#three-veto-decisions-nie-an-die-ki-delegiert |

## Criterion 1
Awarded anchor: "Drei bis fünf Kernfunktionen als Use-Cases mit Akteuren und fachlichem Nutzen; Stakeholder identifiziert; Anforderungen eindeutig und widerspruchsfrei."
Evidence: docs/arc42/01-introduction-goals.md#use-case-catalogue
Justification: Fünf Kernfunktionen sind mit Actor, Trigger, Outcome und Nutzenkette dokumentiert.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 2
Awarded anchor: "Mindestens drei NfA, jede mit messbarem Zielwert und Messverfahren; Bezug zu den Architekturentscheidungen erkennbar (ADR)."
Evidence: docs/arc42/10-quality-requirements.md#quality-goals-smart-nfrs
Justification: Die NfA-Tabelle erfüllt Zielwert, Messverfahren und ADR-Bezug schriftlich.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 3
Awarded anchor: "Klare Problemstellung; Vision mit Zielgruppe, realem oder plausiblem Bedürfnis und Abgrenzung; je ein Satz zum KI-Nutzen pro Kernfunktion."
Evidence: docs/arc42/01-introduction-goals.md#vision
Justification: Problemstellung, Zielgruppe, Bedürfnis, Abgrenzung und KI-Nutzen pro Kernfunktion sind ausdrücklich vorhanden.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 4
Awarded anchor: "C4-Ebenen 1 und 2 (oder gleichwertige Sichten) vorhanden; Begründung des Architekturstils teilweise; kleinere Inkonsistenzen zwischen Bild und Text; roter Faden mehrheitlich erkennbar, einzelne Brüche."
Evidence: docs/arc42/05-building-block-view.md#level-0-system-context
Justification: C4 und ADR-Stilbegründung sind vorhanden, aber kleinere Inkonsistenzen blockieren die volle konjunktive Stufe.
Gaps:
- §5 nennt `parsers/fhir_parser.py`, im Service-Layout ist kein solcher Parser vorhanden.
- Der rote Faden ist mehrheitlich, aber nicht risikofrei vollständig nachweisbar.

## Criterion 5
Awarded anchor: "Zwei Perspektiven mit Diagramm und Text abgedeckt."
Evidence: docs/arc42/05-building-block-view.md#level-1-containers; docs/arc42/06-runtime-view.md#scenario-1-harmonise-to-freeze
Justification: Struktur und Verhalten sind sauber belegt; Interaktion bleibt gegenüber dem Top-Anker zu schwach.
Gaps:
- Die Interaktionsperspektive ist als Use-Case-Diagramm belegt, nicht als vollständiger Schnittstellen-Vertrag.
- OpenAPI/Interface-Verträge sind nicht als eigene Perspektive mit Diagramm und erläuterndem Text ausgearbeitet.

## Criterion 6
Awarded anchor: "Relationales Modell vollständig inkl. Migrations-Skripten; Einsatz der Vektor-Datenbank dokumentiert."
Evidence: docs/arc42/05-building-block-view.md#data-model; db/schema.sql
Justification: ER-Modell, Schema, Migrationen und pgvector-Einsatz sind vorhanden.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 7
Awarded anchor: "Einheitliche Struktur mit klaren Verantwortlichkeiten; sprechende Namen; Dokumentation an nicht-trivialen Stellen; Modulgrenzen im Code konsistent zum Entwurf."
Evidence: docs/arc42/05-building-block-view.md#level-1-containers; services/
Justification: Services, Pakete und zentrale Module folgen den dokumentierten Verantwortlichkeiten.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 8
Awarded anchor: "Framework-Mittel durchgehend idiomatisch (Dependency Injection, externalisierte Konfiguration, einheitliche Fehlerbehandlung, Validierung); Framework-Wahl im Bericht begründet."
Evidence: docs/arc42/08-crosscutting-concepts.md#modern-application-concepts
Justification: DI, REST/OpenAPI, Pydantic, Env-Konfiguration und Fehlerbehandlung sind konkret dem Code zugeordnet.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 9
Awarded anchor: "Konkrete Erkenntnisse mit Belegen (Diffs oder Commit-Referenzen), insbesondere wo KI-Vorschläge angenommen, korrigiert oder verworfen wurden."
Evidence: LEARNINGS.md#learnings
Justification: Learnings sind projektbezogen, PR/SHA-belegt und mit KI-Dispositionen markiert.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 10
Awarded anchor: "Repository-URL im Bericht, Repository zugänglich, Quellcode vollständig."
Evidence: docs/index.md#tarifhub-architecture-documentation
Justification: Die Abgabeseite enthält die GitHub-URL; der Checkout enthält den Quellcode.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 11
Awarded anchor: "Prüfbare Abnahmekriterien pro Kernfunktion, inkl. Bezug zu den Qualitätsanforderungen (Kriterium 2)."
Evidence: docs/arc42/10-quality-requirements.md#acceptance-criteria
Justification: Given/When/Then-Kriterien sind beobachtbar und referenzieren NfA.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 12
Awarded anchor: "Teststufen (Unit, Integration, ggf. Ende-zu-Ende) mit Werkzeugen benannt und begründet; Tests der KI-Anteile berücksichtigt (z. B. Guardrail-Verhalten, Umgang mit nicht-deterministischen Antworten)."
Evidence: docs/arc42/13-test-strategy.md#tests-der-ki-anteile
Justification: Testpyramide, CI, Cross-Engine-Parity und KI-Tests sind benannt und begründet.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 13
Awarded anchor: "Tests decken die Kernlogik ab, inkl. Fehlerfälle; Tests laufen im Build durch."
Evidence: docs/arc42/10-quality-requirements.md#unit-and-contract-tests-offline-suite; services/*/tests
Justification: Dokumentierte Testzahlen, Fehlerfälle und CI-Schritte decken Kernlogik ab.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 14
Awarded anchor: "Ergebnisse nachvollziehbar dokumentiert (Testbericht oder Pipeline-Ausgabe) und im Bericht interpretiert."
Evidence: docs/arc42/10-quality-requirements.md#test-and-pipeline-results
Justification: Ausgaben sind zitiert und fachlich interpretiert, nicht nur behauptet.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 15
Awarded anchor: "Einsatz pro Phase beschrieben; Belege nur teilweise; Erklärung der Eigenständigkeit vorhanden."
Evidence: docs/method/ai-tools.md#generierung; docs/method/ai-tools.md#erklaerung-der-eigenstaendigkeit
Justification: Phasen und Belege sind stark, aber die Eigenständigkeitserklärung ist ausdrücklich nicht final.
Gaps:
- Erklärung der Eigenständigkeit ist ein Platzhalter.
- Unterschrift, finales Owner-Wording und damit die vollständige Erklärung fehlen.

## Criterion 16
Awarded anchor: "Mindestens zwei KI-Rollen substanziell in der Lösung (z. B. LLM-gestützte Verarbeitung plus Embedding-Suche oder Agent); Guardrails greifen; wo sinnvoll Human-in-the-Loop."
Evidence: docs/arc42/10-quality-requirements.md#harmonisation-results
Justification: `ai_map`, Embedding-Suche, Guardrails und Review-Queue sind substanziell belegt.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 17
Awarded anchor: "Klare Modul- bzw. Service-Grenzen konsistent zum Entwurf; Lösung lauffähig per Compose oder Kubernetes; Wahl des Stils (modularer Monolith oder verteilt) begründet."
Evidence: docs/arc42/07-deployment-view.md#evidence-2-the-full-stack-runs-under-compose
Justification: Compose, CI-Images, Helm/k3d und Distributed-Service-Begründung erfüllen den Anker.
Gaps:
- Keine, höchste Stufe erreicht.

## Criterion 18
Awarded anchor: "Reflexion vorhanden, teilweise generisch; Veto-Entscheidungen benannt, aber ohne Belegtiefe."
Evidence: docs/method/fazit.md#three-veto-decisions-nie-an-die-ki-delegiert
Justification: Drei Vetos und Transfer sind vorhanden, aber Veto 3 ist vor Abgabe nur begrenzt artefaktisch belegt.
Gaps:
- Veto 3 ist nicht als abgeschlossener Vorgang belegbar.
- Die Belegtiefe ist nicht für alle drei Vetos gleich stark.

This is an estimate produced by a model, not the human grader.
