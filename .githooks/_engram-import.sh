#!/usr/bin/env bash
# Shared by the git hooks: imports the project memory chunks in .engram/ into the local Engram DB.
# Imports only this project's chunks; never uses --all.
cd "$(git rev-parse --show-toplevel)" || exit 0

if [ ! -d .engram ]; then
  exit 0
fi

if ! command -v engram >/dev/null 2>&1; then
  echo "[engram] No se encontró 'engram'; la memoria del equipo no se importó. Instalalo y corré: engram sync --import"
  exit 0
fi

if engram sync --import >/dev/null 2>&1; then
  echo "[engram] Memoria del equipo importada."
else
  echo "[engram] No se pudo importar la memoria. Probá a mano: engram sync --import"
fi
exit 0
