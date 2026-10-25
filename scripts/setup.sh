#!/usr/bin/env bash
# One-time setup after cloning the repository. Safe to run again.
#   1. Activates the versioned git hooks (.githooks/) so every `git pull` imports Engram memory.
#   2. Restores the project skills listed in skills-lock.json into .agents/skills/ (+ .claude/skills/ links).
#   3. Imports the team's Engram memory from .engram/.
set -u
cd "$(git rev-parse --show-toplevel)" || { echo "Ejecutá este script dentro del repositorio."; exit 1; }

echo "== 1/3 Hooks de git"
git config core.hooksPath .githooks
chmod +x .githooks/* scripts/*.sh 2>/dev/null || true
echo "   core.hooksPath = .githooks (cada 'git pull' importa la memoria de engram)"

echo "== 2/3 Skills del proyecto"
if command -v npx >/dev/null 2>&1; then
  if npx -y skills experimental_install; then
    echo "   Skills restauradas en .agents/skills/ desde skills-lock.json"
  else
    echo "   No se pudieron restaurar las skills. Reintentá: npx -y skills experimental_install"
  fi
else
  echo "   Falta Node.js/npx: instalalo y corré 'npx -y skills experimental_install'"
fi
# Claude Code reads project skills from .claude/skills/; the restore only fills .agents/skills/.
mkdir -p .claude/skills
for dir in .agents/skills/*/; do
  name=$(basename "$dir")
  [ -e ".claude/skills/$name" ] && continue
  ln -s "../../.agents/skills/$name" ".claude/skills/$name" 2>/dev/null \
    || cp -r ".agents/skills/$name" ".claude/skills/$name"
done
echo "   Skills disponibles para Claude Code en .claude/skills/: $(ls .claude/skills | wc -l)"

echo "== 3/3 Memoria de engram"
if command -v engram >/dev/null 2>&1; then
  if engram sync --import; then
    echo "   Memoria del equipo importada."
  else
    echo "   No se pudo importar. Reintentá: engram sync --import"
  fi
else
  echo "   Falta engram (https://github.com/Gentleman-Programming/engram). Instalalo y corré: engram sync --import"
fi

echo
echo "Listo. Próximo paso: cp env.example .env (cuando exista, desde EJ-1) y seguí CHANGES.md."
