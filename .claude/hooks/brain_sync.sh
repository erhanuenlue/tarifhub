#!/usr/bin/env bash
# SessionEnd: keep the second brain alive with zero manual steps.
# 1) Regenerates vault/00-index.md (the MOC): ADRs from docs/adr, journal entries,
#    learnings, decision matrix, fazit notes — so Obsidian always has a current map.
# 2) If OBSIDIAN_VAULT is set (in .env or the environment), mirrors the knowledge set
#    into "<OBSIDIAN_VAULT>/tarifhub/" (one-way: repo → vault; repo stays the source of truth).
# Quiet, idempotent, never blocks.
set -uo pipefail

# --debounce (Stop-hook mode): skip if rebuilt <5 min ago — keeps long sessions fresh
# without churning every turn. SessionEnd invokes without the flag and always runs.
MARK="vault/.brain_sync_last"
if [ "${1:-}" = "--debounce" ] && [ -f "$MARK" ]; then
  now=$(date +%s)
  last=$(stat -c %Y "$MARK" 2>/dev/null || stat -f %m "$MARK" 2>/dev/null || echo 0)
  case "$last" in *[!0-9]*) last=0;; esac
  [ $((now - last)) -lt 300 ] && exit 0
fi

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
    title=$(head -1 "$f" | sed 's/^#\+ *//; s/[][|]//g')
    echo "- [[$(basename "$f" .md)|${title}]]"
    found=1
  done
  [ $found -eq 0 ] && echo "- *(none materialised yet — prompts/02 creates ADR-001…014 from the architecture register)*"
  echo
  echo "## AI-workflow journal (CAS criterion 15 — contemporaneous)"
  echo
  n=$(ls vault/daily/*.md 2>/dev/null | wc -l | tr -d ' ')
  echo "- **${n} entries.** Latest:"
  for f in $(ls vault/daily/*.md 2>/dev/null | sort | tail -5); do
    echo "  - [[$(basename "$f" .md)]]"
  done
  echo
  echo "## Reflection material"
  echo
  [ -f vault/vault-rules.md ] && echo "- [[vault-rules|Vault rules — what feeds which criterion]]"
  [ -f vault/decision-matrix.md ] && echo "- [[decision-matrix|Decision matrix — Vibe vs Spec-Driven vs Agentic]]"
  [ -f vault/fazit-notes.md ] && echo "- [[fazit-notes|Fazit notes (raw, running)]] — $(grep -c '^- ' vault/fazit-notes.md 2>/dev/null || echo 0) observations"
  [ -f LEARNINGS.md ] && echo "- [[LEARNINGS|LEARNINGS.md (criterion 9)]] — $(grep -c '^#\#\|^- ' LEARNINGS.md 2>/dev/null || echo 0) items"
  echo
  echo "## Architecture (source of truth)"
  echo
  arcline=""
  for f in docs/arc42/[0-9]*.md; do
    [ -f "$f" ] || continue
    num=$(basename "$f" | cut -d- -f1 | sed 's/^0//')
    arcline="${arcline}[[$(basename "$f" .md)|§${num}]] · "
  done
  if [ -n "$arcline" ]; then
    echo "- arc42: ${arcline%· } — site: \`mkdocs serve -f docs/mkdocs.yml\`"
  else
    echo "- arc42 chapters: \`docs/arc42/\` — site: \`mkdocs serve -f docs/mkdocs.yml\`"
  fi
  echo "- Last docs change: $(git log -1 --format='%ad · %s' --date=short -- docs/ 2>/dev/null || echo 'no commits yet')"
} > "$IDX"
rm -f vault/graph.md

# Optional one-way mirror into an external Obsidian vault
if [ -n "${OBS:-}" ] && [ -d "$OBS" ]; then
  DEST="$OBS/tarifhub"
  mkdir -p "$DEST/adr" "$DEST/vault"
  cp -f docs/adr/*.md "$DEST/adr/" 2>/dev/null
  cp -Rf vault/. "$DEST/vault/" 2>/dev/null
  [ -f LEARNINGS.md ] && cp -f LEARNINGS.md "$DEST/"
  echo "brain_sync: mirrored to $DEST"
fi
mkdir -p vault && touch "$MARK"
exit 0
