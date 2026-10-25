#!/usr/bin/env bash
# Exports this project's new Engram memories to .engram/ and commits them.
# Run it before `git push` so the next teammate gets your memory on `git pull`.
# Never uses --all: only this project's memory is exported.
set -eu
cd "$(git rev-parse --show-toplevel)"

if ! command -v engram >/dev/null 2>&1; then
  echo "Falta engram; no hay memoria para exportar."
  exit 1
fi

engram sync
git add .engram
if git diff --cached --quiet -- .engram; then
  echo "No hay memoria nueva para commitear."
else
  git commit -m "chore(engram): sync project memory" -- .engram
  echo "Memoria commiteada. Ahora: git push"
fi
