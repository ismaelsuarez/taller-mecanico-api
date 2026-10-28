"""Contratos D1 de EJ-5: alta de personal, roles, eventos y lo propio (sin BD)."""

import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.usuarios import schemas

DATO_PRIVADO = secrets.token_hex(16)
ALTA_BASE = {
    "email": "trabajador@example.com",
    "nombre": "Trabajador Nuevo",
    "password_provisoria": "provisoria-123",
    "rol": "RECEPCION",
}


def test_alta_valida_se_acepta_sin_normalizar():
    entrada = schemas.AltaPersonalEntrada.model_validate(ALTA_BASE)
    assert entrada.model_dump() == ALTA_BASE


def test_alta_exige_exactamente_sus_campos_sin_hash():
    esquema = schemas.AltaPersonalEntrada.model_json_schema()
    assert esquema["additionalProperties"] is False
    assert set(esquema["required"]) == {"email", "nombre", "password_provisoria", "rol"}
    assert "password_hash" not in esquema["properties"]
    assert "password" not in esquema["properties"]


@pytest.mark.parametrize("rol", ["CLIENTE", "cliente", "SUPERVISOR", "", "ADMIN "])
def test_alta_rechaza_rol_no_personal(rol):
    with pytest.raises(ValidationError) as error:
        schemas.AltaPersonalEntrada.model_validate(ALTA_BASE | {"rol": rol})
    detalle = error.value.errors()[0]
    assert detalle["loc"] == ("rol",)
    assert detalle["type"] == "literal_error"


@pytest.mark.parametrize("extra", ["id", "password_hash", "debe_cambiar_password", "activo"])
def test_alta_rechaza_campo_extra(extra):
    with pytest.raises(ValidationError) as error:
        schemas.AltaPersonalEntrada.model_validate(ALTA_BASE | {extra: "no permitido"})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("clave,aceptada", [("x" * 72, True), ("x" * 73, False)])
def test_alta_password_provisoria_limite_utf8(clave, aceptada):
    entrada = ALTA_BASE | {"password_provisoria": clave}
    if aceptada:
        assert schemas.AltaPersonalEntrada.model_validate(entrada).password_provisoria == clave
    else:
        with pytest.raises(ValidationError):
            schemas.AltaPersonalEntrada.model_validate(entrada)


@pytest.mark.parametrize("rol", ["ADMIN", "RECEPCION", "MECANICO", "CLIENTE"])
def test_asignacion_acepta_los_cuatro_roles_del_check(rol):
    entrada = schemas.AsignacionRolEntrada.model_validate({"rol": rol})
    assert entrada.model_dump() == {"rol": rol, "vence_en": None}


@pytest.mark.parametrize("extra", ["desde", "revocada_en", "otorgada_por", "id"])
def test_asignacion_rechaza_campo_extra(extra):
    with pytest.raises(ValidationError) as error:
        schemas.AsignacionRolEntrada.model_validate({"rol": "ADMIN", extra: None} | {})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_asignacion_rechaza_rol_fuera_del_check():
    with pytest.raises(ValidationError) as error:
        schemas.AsignacionRolEntrada.model_validate({"rol": "SUPERVISOR"})
    assert error.value.errors()[0]["loc"] == ("rol",)


def test_vence_en_futuro_con_zona_se_acepta():
    futuro = datetime.now(UTC) + timedelta(hours=1)
    entrada = schemas.AsignacionRolEntrada.model_validate(
        {"rol": "MECANICO", "vence_en": futuro.isoformat()}
    )
    assert entrada.vence_en == futuro


def test_vence_en_pasado_responde_error_de_validacion():
    pasado = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(ValidationError) as error:
        schemas.AsignacionRolEntrada.model_validate(
            {"rol": "MECANICO", "vence_en": pasado.isoformat()}
        )
    detalle = error.value.errors()[0]
    assert detalle["loc"] == ("vence_en",)
    assert detalle["type"] == "value_error"
    assert "posterior" in detalle["msg"]


def test_vence_en_sin_zona_horaria_responde_error_de_validacion():
    futuro_sin_zona = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)
    with pytest.raises(ValidationError) as error:
        schemas.AsignacionRolEntrada.model_validate(
            {"rol": "MECANICO", "vence_en": futuro_sin_zona.isoformat()}
        )
    detalle = error.value.errors()[0]
    assert detalle["loc"] == ("vence_en",)
    assert detalle["type"] == "value_error"
    assert "zona horaria" in detalle["msg"]


def test_rol_asignado_proyecta_solo_sus_campos():
    origen = SimpleNamespace(
        id=9, usuario_id=1, rol="ADMIN", desde=datetime(2026, 1, 1, tzinfo=UTC),
        vence_en=None, revocada_en=None, otorgada_por=1, token=DATO_PRIVADO,
    )
    salida = schemas.RolAsignadoLectura.model_validate(origen, from_attributes=True)
    assert salida.model_dump(mode="json") == {
        "rol": "ADMIN",
        "desde": "2026-01-01T00:00:00Z",
        "vence_en": None,
        "otorgada_por": 1,
    }


def test_roles_asignados_envuelve_items():
    salida = schemas.RolesAsignadosLectura(items=[
        schemas.RolAsignadoLectura(
            rol="CLIENTE", desde=datetime(2026, 1, 1, tzinfo=UTC),
            vence_en=None, otorgada_por=None,
        )
    ])
    assert set(salida.model_dump(mode="json")) == {"items"}
    assert salida.model_dump(mode="json")["items"][0]["rol"] == "CLIENTE"


def test_evento_proyecta_solo_id_cuando_actor_y_accion():
    origen = SimpleNamespace(
        id=3, cuando=datetime(2026, 2, 1, 12, tzinfo=UTC),
        actor="admin@example.com", accion="Alta de personal con rol ADMIN",
        password=DATO_PRIVADO,
    )
    salida = schemas.EventoLectura.model_validate(origen, from_attributes=True)
    assert salida.model_dump(mode="json") == {
        "id": 3,
        "cuando": "2026-02-01T12:00:00Z",
        "actor": "admin@example.com",
        "accion": "Alta de personal con rol ADMIN",
    }


def test_evento_rechaza_campos_extra():
    with pytest.raises(ValidationError) as error:
        schemas.EventoLectura.model_validate(
            {"id": 1, "cuando": datetime.now(UTC), "actor": "a", "accion": "b", "detalle": "x"}
        )
    assert error.value.errors()[0]["type"] == "extra_forbidden"
