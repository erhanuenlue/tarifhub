# Zusammenfassung (Deutsch)

## Vision und Problemstellung

Die ambulanten Tarifdaten der Schweiz sind fragmentiert. Rund 110 aktive Tariftypen
erscheinen über mehr als 20 Quellen in den Formaten XLSX, XML, PDF und FHIR, ohne eine
einzige massgebliche Maschinenschnittstelle. Die Folgekosten summieren sich stromabwärts:
jeder PIS/HIS-Anbieter implementiert das Parsen pro Quelle neu, Tarifwerte erreichen die
Abrechnungssysteme ohne nachweisbare Herkunft, Versionswechsel werden von Hand abgeglichen,
und ein unentdeckter Mapping-Fehler wird stillschweigend zu einer falschen Rechnung. TarifHub
führt diese Daten in eine kanonische, versionierte und deterministische Schnittstelle zusammen.
Zielgruppe sind PIS/HIS-Anbieter als maschinelle Konsumenten (REST/OpenAPI und FHIR R4), die
Tarifexpertinnen und -experten, welche unsichere Mappings prüfen, Praxisnutzende, die in der
TarifGuard-Konsole nachschlagen, sowie KI-Agenten, die freigegebene Daten über MCP lesen. Der
Kern ist die Zusicherung, dass ein ausgelieferter Wert nachweisbar genau der Wert ist, der
geprüft und eingefroren wurde.

## Architektur

Das System gliedert sich in vier Schichten, getrennt durch eine erzwungene Freeze-Line.
Oberhalb der Linie liegt die KI-gestützte Harmonisierung (L0): Adapter, Parser, das
Mapping in das kanonische Datenmodell `TariffRecord`, die deterministische Validierung und das Scoring.
Unterhalb der Linie liegt die deterministische, ausschliesslich lesende Serving-API (L1,
TarifCore mit REST und FHIR R4, Point-in-Time- und Diff-Abfragen) samt den lesenden
MCP-Werkzeugen (TarifMCP). Darüber sitzen die Regeln (L2, nach dem CAS) und die
Demo-Konsole (L3, TarifGuard). Eingefrorene Datensätze sind unveränderlich: ein SHA-256
`record_hash` über den sortierten kanonischen Inhalt versiegelt sie, Aktualisierungen
erzeugen neue Versionen, und das `audit_log` ist ausschliesslich anhängend. Persistenz und
mehrsprachige semantische Suche laufen auf PostgreSQL 16 mit pgvector (HNSW, Cosinus,
multilingual-e5, 1024 Dimensionen); für Offline-Tests dient ein SQLite-Spiegel.

## KI-Einsatz

KI wirkt nur an zwei klar abgegrenzten Stellen. Erstens vor dem Freeze in `ai_map`: ein
einziger Seam füllt ausschliesslich fehlende, nicht abrechnungsrelevante Felder mit
schema-gebundener strukturierter Ausgabe (fill-only); fehlt ein API-Schlüssel, greift
deterministisch `map_raw`. Zweitens in Such- und Erklärungs-Seams, die Werte ausschliesslich
lesen und nie verändern. Der Build selbst ist mehragentig: modellgebundene Worker
implementieren und prüfen, ein unabhängiges Zweitmodell (Codex gpt-5.5) begutachtet als
zweite Modellfamilie jeden Pull Request. So fing das Zweitmodell etwa einen Metadaten-Schreibvorgang,
der die Idempotenz des erneuten Imports brach, sowie ein `json.loads` auf einer Postgres-JSONB-Spalte,
das jede Antwort mit Status 500 hätte scheitern lassen, obwohl 28 grüne Tests beides übersahen.

## Fazit-Kernaussage

Nicht die KI macht Abrechnungsdaten beherrschbar, sondern die Grenze um sie herum. Eine
erzwungene, getestete Determinismusgrenze (ein AST-Test in der CI, der jeden LLM-Client auf
dem Wertpfad verbietet, plus der `guard_frozen`-Hook, der eine fehlerhafte Bearbeitung
unterhalb der Linie tatsächlich stoppte) ist genau das, was den Einsatz von KI auf
Abrechnungsdaten überhaupt verantwortbar und nutzbar macht. KI darf oberhalb der Linie
Geschwindigkeit und Breite liefern; unterhalb der Linie bleibt der Wert deterministisch,
nachvollziehbar und menschlich verantwortet.
