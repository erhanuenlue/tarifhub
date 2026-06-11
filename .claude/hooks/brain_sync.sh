#!/usr/bin/env bash
# SessionEnd: keep the second brain alive with zero manual steps.
# 1) Regenerates vault/00-index.md (the MOC): ADRs from docs/adr, journal entries,
#    learnings, decision matrix, fazit notes — so Obsidian always has a current map.
# 2) If OBSIDIAN_VAULT is set (in .env or the environment), mirrors the knowledge set
#    into "<OBSIDIAN_VAULT>/tarifhub/" (one-way: repo → vault; repo stays the source of truth).
# Quiet, idempotent, never blocks.
set -uo pipefail

# pick up OBSIDIAN_VAULT from .env without sourcing secrets into the environment log
OBS="${OBSIDIAN_VAULT:-$(grep -E '^OBSIDIAN_VAULT=' .env 2>/dev/null | cut -d= -f2- | tr -d '"' )}"

IDX="vault/00-index.md"
mkdir -p vault/daily

{
  echo "# tarifhub — knowledge index (auto-generated)"
  echo
  echo "> Rebuilt by the \`brain_sync\` hook at every session end ($(date '+%Y-%m-%d %H:%M')). Do not edit by hand — edit the sources."
  echo
  echo "## Decisions (ADRs)"
  echo
  found=0
  for f in docs/adr/[0-9]*.md; do
    [ -f "$f" ] || continue
    title=$(head -1 "$f" | sed 's/^#\+ *//')
    echo "- [${title}](../docs/adr/$(basename "$f"))"
    found=1
  done
  [ $found -eq 0 ] && echo "- *(none materialised yet — prompts/02 creates ADR-001…014 from the architecture register)*"
  echo
  echo "## AI-workflow journal (CAS criterion 15 — contemporaneous)"
  echo
  n=$(ls vault/daily/*.md 2>/dev/null | wc -l | tr -d ' ')
  echo "- **${n} entries.** Latest:"
  for f in $(ls vault/daily/*.md 2>/dev/null | sort | tail -5); do
    echo "  - [$(basename "$f" .md)](daily/$(basename "$f"))"
  done
  echo
  echo "## Reflection material"
  echo
  [ -f vault/vault-rules.md ] && echo "- [Vault rules — what feeds which criterion](vault-rules.md)"
  [ -f vault/decision-matrix.md ] && echo "- [Decision matrix — Vibe vs Spec-Driven vs Agentic](decision-matrix.md)"
  [ -f vault/fazit-notes.md ] && echo "- [Fazit notes (raw, running)](fazit-notes.md) — $(grep -c '^- ' vault/fazit-notes.md 2>/dev/null || echo 0) observations"
  [ -f LEARNINGS.md ] && echo "- [LEARNINGS.md (criterion 9)](../LEARNINGS.md) — $(grep -c '^#\#\|^- ' LEARNINGS.md 2>/dev/null || echo 0) items"
  echo
  echo "## Architecture (source of truth)"
  echo
  echo "- [arc42 chapters](../docs/arc42/) — site: \`mkdocs serve -f docs/mkdocs.yml\`"
  echo "- Last docs change: $(git log -1 --format='%ad · %s' --date=short -- docs/ 2>/dev/null || echo 'no commits yet')"
} > "$IDX"

# Optional one-way mirror into an external Obsidian vault
if [ -n "${OBS:-}" ] && [ -d "$OBS" ]; then
  DEST="$OBS/tarifhub"
  mkdir -p "$DEST/adr" "$DEST/vault"
  cp -f docs/adr/*.md "$DEST/adr/" 2>/dev/null
  cp -Rf vault/. "$DEST/vault/" 2>/dev/null
  [ -f LEARNINGS.md ] && cp -f LEARNINGS.md "$DEST/"
  echo "brain_sync: mirrored to $DEST"
fi
exit 0
