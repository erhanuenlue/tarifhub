#!/usr/bin/env bash
# render.sh — render every docs/diagrams/*.puml to SVG next to its source.
#
# Run from the repo root:
#   bash docs/diagrams/render.sh
#
# Uses the official plantuml/plantuml Docker image; the C4 stdlib is bundled
# (plantuml >= 1.2023), so no internet access is needed at render time.
# Shared skinparams live in tarifhub-style.iuml (same directory, picked up
# via relative !include — .iuml files are deliberately not rendered).
set -euo pipefail

DIAGRAMS_DIR="docs/diagrams"

if [[ ! -d "$DIAGRAMS_DIR" ]]; then
  echo "error: $DIAGRAMS_DIR not found — run this script from the repo root." >&2
  exit 1
fi

# Collect sources on the host, then address them by their in-container path
# (/data is the mount of docs/diagrams), so no glob is evaluated inside Docker.
files=()
for f in "$DIAGRAMS_DIR"/*.puml; do
  files+=("/data/$(basename "$f")")
done

if [[ ${#files[@]} -eq 0 ]]; then
  echo "error: no .puml files found in $DIAGRAMS_DIR" >&2
  exit 1
fi

echo "Rendering ${#files[@]} PlantUML file(s) to SVG ..."
docker run --rm -v "$(pwd)/$DIAGRAMS_DIR:/data" plantuml/plantuml -tsvg -o /data "${files[@]}"
echo "Done — SVGs written next to their sources in $DIAGRAMS_DIR/."

# er-data-model.svg is rendered from Graphviz, not PlantUML. The committed SVG
# is current; re-render only after editing er-data-model.dot:
#   dot -Tsvg docs/diagrams/er-data-model.dot -o docs/diagrams/er-data-model.svg
