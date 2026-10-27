"""JWT reales por la interfaz pública; reloj controlado, firma nunca simulada."""

import secrets
from datetime import UTC, datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.config import cargar_settings


@pytest.fixture
def configuracion(configurar_entorno):
    configurar_entorno(JWT_SECRET=secrets.token_hex(32), ACCESS_TOKEN_EXPIRE_SECONDS=str(90))
    return cargar_settings(None)


@pytest.mark.parametrize("algoritmo", ["HS256", "HS384"])
def test_emitir_usa_configuracion_y_claims_fraccionales(configuracion, algoritmo):
    configuracion.jwt_algorithm = algoritmo
    instante = datetime.now(UTC) - timedelta(seconds=1)
    token = security.emitir_token(7, ["CLIENTE"], configuracion, emitido_en=instante)
    claims = jwt.decode(
        token, configuracion.jwt_secret.get_secret_value(), algorithms=[algoritmo],
        options={"require": ["sub", "iat", "exp", "roles"]},
    )

    assert claims == {
        "sub": "7", "iat": instante.timestamp(),
        "exp": instante.timestamp() + 90, "roles": ["CLIENTE"],
    }
    assert isinstance(claims["iat"], float)
    assert jwt.get_unverified_header(token)["alg"] == algoritmo


def test_verificar_reutiliza_clave_fija_sin_issuer_ni_audience(configuracion):
    token = security.emitir_token(7, [], configuracion)
    claims = security.verificar_token(token, cargar_settings(None))
    assert claims["sub"] == "7" and claims["roles"] == []


@pytest.mark.parametrize("caso", ["firma", "algoritmo", "sin_firma", "malformado", "alterado"])
def test_verificar_rechaza_criptografia_invalida(configuracion, caso):
    ahora = datetime.now(UTC).timestamp()
    claims = {"sub": "7", "iat": ahora, "exp": ahora + 90, "roles": []}
    clave = configuracion.jwt_secret.get_secret_value()
    algoritmo = configuracion.jwt_algorithm
    if caso == "firma":
        clave = secrets.token_hex(32)
    elif caso == "algoritmo":
        algoritmo = "HS384"
    elif caso == "sin_firma":
        clave, algoritmo = "", "none"
    token = jwt.encode(claims, clave, algorithm=algoritmo)
    if caso == "malformado":
        token = secrets.token_urlsafe(16)
    elif caso == "alterado":
        cabecera, cuerpo, firma = token.split(".")
        firma = ("A" if firma[0] != "A" else "B") + firma[1:]
        token = ".".join((cabecera, cuerpo, firma))

    with pytest.raises(security.TokenInvalido, match="La sesión no es válida"):
        security.verificar_token(token, configuracion)


@pytest.fixture
def reloj(monkeypatch):
    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, 0, 0, 0, 500000, tzinfo=UTC)

    monkeypatch.setattr(security, "datetime", Reloj)
    monkeypatch.setattr(jwt.api_jwt, "datetime", Reloj)


@pytest.fixture
def claims_validos(reloj):
    return {"sub": "7", "iat": 1767225600.125, "exp": 1767225690.125, "roles": ["CLIENTE"]}


@pytest.mark.parametrize("campo", ["sub", "iat", "exp", "roles"])
def test_rechaza_claim_ausente(configuracion, claims_validos, campo):
    del claims_validos[campo]
    token = jwt.encode(claims_validos, configuracion.jwt_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(security.TokenInvalido):
        security.verificar_token(token, configuracion)


@pytest.mark.parametrize("campo,valor", [
    ("sub", 7), ("sub", None), ("sub", ""), ("sub", "no-es-un-id"),
    ("roles", "ADMIN"), ("roles", None), ("roles", [1]), ("roles", {}),
    *[(campo, valor) for campo in ("iat", "exp") for valor in (
        None, True, "1767225600.125", [], {}, float("nan"), float("inf"), 10**400,
    )],
])
def test_rechaza_tipos_invalidos_sin_coercion(configuracion, claims_validos, campo, valor):
    claims_validos[campo] = valor
    token = jwt.encode(claims_validos, configuracion.jwt_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(security.TokenInvalido):
        security.verificar_token(token, configuracion)


@pytest.mark.parametrize("campo,valor,valido", [
    ("exp", 1767225600.875, True),  # Todavía no venció: no truncar a .000.
    ("exp", 1767225600.500, False),
    ("exp", 1767225600.125, False),
    ("iat", 1767225600.875, False),  # Aún no emitido, dentro del mismo segundo.
])
def test_validar_tiempos_sin_truncar(configuracion, claims_validos, campo, valor, valido):
    claims_validos[campo] = valor
    token = jwt.encode(claims_validos, configuracion.jwt_secret.get_secret_value(), algorithm="HS256")
    if valido:
        assert security.verificar_token(token, configuracion)[campo] == valor
    else:
        with pytest.raises(security.TokenInvalido):
            security.verificar_token(token, configuracion)


def test_dos_emisiones_en_el_mismo_segundo_conservan_orden_exacto(configuracion, reloj):
    instantes = [
        datetime(2026, 1, 1, 0, 0, 0, 125000, tzinfo=UTC),
        datetime(2026, 1, 1, 2, 0, 0, 375000, tzinfo=timezone(timedelta(hours=2))),
    ]
    tokens = [security.emitir_token(7, ["CLIENTE"], configuracion, emitido_en=t) for t in instantes]
    anterior, nuevo = [security.verificar_token(t, configuracion) for t in tokens]
    cambio_utc = datetime(2026, 1, 1, 0, 0, 0, 250000, tzinfo=UTC)

    assert tokens[0] != tokens[1]
    assert (anterior["iat"], nuevo["iat"]) == (1767225600.125, 1767225600.375)
    assert anterior["iat"] < cambio_utc.timestamp() <= nuevo["iat"]
    assert (anterior["exp"], nuevo["exp"]) == (1767225690.125, 1767225690.375)


def test_emision_rechaza_fecha_sin_zona(configuracion):
    with pytest.raises(ValueError, match="zona horaria"):
        security.emitir_token(7, [], configuracion, emitido_en=datetime(2026, 1, 1))
