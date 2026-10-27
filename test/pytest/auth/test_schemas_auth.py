"""Contratos públicos de EJ-4: formas JSON, entradas estrictas y proyección segura."""

import secrets
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.usuarios import schemas

DATO_PRIVADO = secrets.token_hex(16)
ENTRADAS = [
    ("RegistroEntrada", {
        "email": "Persona@Example.COM", "password": "x", "nombre": "Persona",
        "documento": "DNI-100", "telefono": "11-100",
    }),
    ("LoginEntrada", {"email": "Persona@Example.COM", "password": "x"}),
    ("CambioPasswordEntrada", {"password_actual": "x", "password_nueva": "y"}),
]


@pytest.mark.parametrize("nombre,datos", ENTRADAS)
def test_entrada_conserva_datos_sin_normalizar_ni_exigir_complejidad(nombre, datos):
    assert getattr(schemas, nombre).model_validate(datos).model_dump() == datos


@pytest.mark.parametrize("nombre,datos", ENTRADAS)
def test_json_schema_documenta_campos_y_limite_en_bytes(nombre, datos):
    esquema = getattr(schemas, nombre).model_json_schema()
    assert esquema["additionalProperties"] is False
    assert set(esquema["required"]) == set(datos)
    for campo in datos:
        if campo.startswith("password"):
            assert "72 bytes UTF-8" in esquema["properties"][campo]["description"]
            assert "maxLength" not in esquema["properties"][campo]


@pytest.mark.parametrize("nombre,datos", ENTRADAS)
@pytest.mark.parametrize("extra", ["rol", "password_hash", "token"])
def test_entrada_rechaza_extras(nombre, datos, extra):
    with pytest.raises(ValidationError) as error:
        getattr(schemas, nombre).model_validate(datos | {extra: "no permitido"})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("nombre,datos,campo", [
    (nombre, datos, campo) for nombre, datos in ENTRADAS for campo in datos
])
def test_entrada_exige_cada_campo(nombre, datos, campo):
    incompletos = {clave: valor for clave, valor in datos.items() if clave != campo}
    with pytest.raises(ValidationError) as error:
        getattr(schemas, nombre).model_validate(incompletos)
    assert error.value.errors()[0]["loc"] == (campo,)
    assert error.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("nombre,datos,campo", [
    (nombre, datos, campo) for nombre, datos in ENTRADAS for campo in datos
])
@pytest.mark.parametrize("invalido", [None, 123])
def test_entrada_rechaza_tipos_invalidos(nombre, datos, campo, invalido):
    with pytest.raises(ValidationError) as error:
        getattr(schemas, nombre).model_validate(datos | {campo: invalido})
    assert error.value.errors()[0]["loc"] == (campo,)


@pytest.mark.parametrize("nombre,datos,campo", [
    (nombre, datos, campo) for nombre, datos in ENTRADAS
    for campo in datos if campo.startswith("password")
])
@pytest.mark.parametrize("clave,aceptada", [
    ("a" * 72, True), ("a" * 73, False), ("ñ" * 36, True), ("ñ" * 37, False),
    ("", True), (" ", True), ("🔧" * 18, True), ("🔧" * 19, False),
], ids=["72-ascii", "73-ascii", "36-enies", "37-enies", "vacia", "espacio", "18-emoji", "19-emoji"])
def test_password_limite_utf8(nombre, datos, campo, clave, aceptada):
    contrato = getattr(schemas, nombre)
    entrada = datos | {campo: clave}
    if aceptada:
        assert contrato.model_validate(entrada).model_dump()[campo] == clave
    else:
        with pytest.raises(ValidationError) as error:
            contrato.model_validate(entrada)
        detalle = error.value.errors()[0]
        assert detalle["loc"] == (campo,)
        assert detalle["msg"].endswith("La contraseña es demasiado larga.")
        assert clave not in detalle["msg"]


@pytest.mark.parametrize("mensaje,pendiente", [
    ("Registro completado", False), ("Sesión iniciada", False),
    ("Sesión iniciada", True), ("Contraseña actualizada", False),
])
def test_salida_sesion_sin_hash_ni_token(mensaje, pendiente):
    esperado = {
        "mensaje": mensaje, "debe_cambiar_password": pendiente,
        "expira_en_segundos": 1800,
    }
    origen = SimpleNamespace(**esperado, password_hash=DATO_PRIVADO, token=DATO_PRIVADO)
    salida = schemas.SesionLectura.model_validate(origen, from_attributes=True)
    assert salida.model_dump(mode="json") == esperado


def test_salida_logout_solo_mensaje():
    origen = SimpleNamespace(mensaje="Sesión cerrada", token=DATO_PRIVADO)
    salida = schemas.MensajeLectura.model_validate(origen, from_attributes=True)
    assert salida.model_dump(mode="json") == {"mensaje": "Sesión cerrada"}


async def test_identidad_proyecta_usuario_sin_hash_y_distingue_roles(crear_usuario_auth):
    usuario, _ = await crear_usuario_auth(email="identidad@example.com")
    origen = SimpleNamespace(
        usuario=usuario, roles_vigentes=["CLIENTE"], roles_token=["CLIENTE", "MECANICO"],
        token=DATO_PRIVADO,
    )
    salida = schemas.IdentidadLectura.model_validate(origen, from_attributes=True)
    assert salida.model_dump(mode="json") == {
        "usuario": {
            "id": usuario.id, "email": "identidad@example.com", "nombre": "Usuario de prueba",
            "debe_cambiar_password": False,
        },
        "roles_vigentes": ["CLIENTE"], "roles_token": ["CLIENTE", "MECANICO"],
    }
