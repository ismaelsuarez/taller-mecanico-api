#!/usr/bin/env bash
# Crea la base de test que usa pytest (POSTGRES_TEST_DB), con el mismo dueño que la de desarrollo.
# La imagen postgres sólo ejecuta este script cuando el volumen de datos está vacío.
set -euo pipefail

if [ -z "${POSTGRES_TEST_DB:-}" ]; then
  echo "POSTGRES_TEST_DB no está definida: no se crea la base de test."
  exit 0
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v base="$POSTGRES_TEST_DB" -v dueno="$POSTGRES_USER" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'base', :'dueno')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'base') \gexec
SQL
echo "Base de test '$POSTGRES_TEST_DB' lista."
