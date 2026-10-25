# Taller Mecánico API

API REST asincrónica para un taller mecánico: clientes y vehículos, órdenes de trabajo, stock de repuestos y control de acceso por roles. Trabajo práctico integrador de **Programación III (UTN)**, capítulos 1 a 6, con FastAPI, SQLModel, SQLAlchemy 2.0 async, PostgreSQL 16 y Alembic.

> La puesta en marcha de la aplicación (entorno virtual, `.env`, Alembic, `seed.py`, Docker) se documenta en el change **EJ-1** (ver [CHANGES.md](CHANGES.md)).

## Primer uso después de clonar (una sola vez)

```bash
git clone https://github.com/ismaelsuarez/taller-mecanico-api.git
cd taller-mecanico-api
bash scripts/setup.sh
```

`scripts/setup.sh`:

1. Activa los hooks versionados (`git config core.hooksPath .githooks`). Desde ahí, **cada `git pull` importa automáticamente la memoria de engram** del equipo (`engram sync --import`).
2. Restaura las skills del proyecto desde `skills-lock.json` en `.agents/skills/` (con enlaces relativos en `.claude/skills/`). No dependen de rutas de ninguna máquina.
3. Importa la memoria de engram que está en `.engram/`.

Requisitos: Git, Node.js (para `npx`) y [engram](https://github.com/Gentleman-Programming/engram). Si falta alguno, el script avisa y sigue.

> Git no activa hooks al clonar (es una protección de seguridad); por eso este paso es manual y se hace una sola vez.

## Flujo de trabajo del equipo (relevos)

Los 8 ejercicios de la consigna son 8 changes **estrictamente secuenciales** (`EJ-1` → `EJ-8`). Uno trabaja a la vez:

```
git pull                                   # trae el código y, por el hook, la memoria de engram
/opsx:propose 0N-nombre-del-change         # ver CHANGES.md
/opsx:apply
# Definition of Done del change (ver CHANGES.md)
/opsx:archive 0N-nombre-del-change
git commit ...                             # incluye el checkbox [x] en CHANGES.md
bash scripts/sync-memoria.sh               # exporta y commitea tu memoria de engram
git push                                   # relevo al siguiente compañero
```

## Dónde está cada cosa

| Ruta | Contenido |
|---|---|
| [docs/](docs/) | Consigna original del trabajo práctico (fuente de verdad) |
| [knowledge-base/](knowledge-base/README.md) | Base de conocimiento: dominio, modelo de datos, reglas, decisiones del equipo |
| [CHANGES.md](CHANGES.md) | Roadmap de los 8 changes y regla de relevo |
| [AGENTS.md](AGENTS.md) / [CLAUDE.md](CLAUDE.md) | Instrucciones y reglas duras para agentes de IA |
| `openspec/` | Specs y changes de OpenSpec |
| `.agents/skills/`, `skills-lock.json` | Skills del proyecto |
| `.engram/` | Memoria del proyecto (engram), compartida por el equipo |
| `.githooks/`, `scripts/` | Hooks de git y scripts de setup y sincronización de memoria |
