@echo off
rem Exports this project's new Engram memories to .engram\ and commits them.
rem Windows version of scripts/sync-memoria.sh: run it before "git push" so the
rem next teammate gets your memory on "git pull". Never uses --all.
setlocal
chcp 65001 >nul

for /f "delims=" %%R in ('git rev-parse --show-toplevel 2^>nul') do set "RAIZ=%%R"
if not defined RAIZ (
  echo Ejecuta este script dentro del repositorio.
  exit /b 1
)
cd /d "%RAIZ%"

where engram >nul 2>nul
if errorlevel 1 (
  echo Falta engram; no hay memoria para exportar.
  exit /b 1
)

engram sync
if errorlevel 1 exit /b 1

git add .engram
git diff --cached --quiet -- .engram
if errorlevel 1 (
  git commit -m "chore(engram): sync project memory" -- .engram
  if errorlevel 1 exit /b 1
  echo Memoria commiteada. Ahora: git push
) else (
  echo No hay memoria nueva para commitear.
)
endlocal
