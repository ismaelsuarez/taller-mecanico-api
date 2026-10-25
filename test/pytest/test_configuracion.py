"""Spec configuracion-aplicacion: configuración leída del entorno y secretos obligatorios."""

from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.core.config import ErrorConfiguracion, cargar_settings

VARIABLES = [
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_TEST_DB",
    "JWT_SECRET",
    "JWT_ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_SECONDS",
    "COOKIE_SECURE",
    "BCRYPT_ROUNDS",
    "BCRYPT_MAX_CONCURRENCY",
    "DB_POOL_SIZE",
    "SQL_ECHO",
]


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    """Ningún test depende de las variables de la máquina ni del .env real."""
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def escribir_env(directorio: Path, **valores: str) -> Path:
    archivo = directorio / ".env"
    archivo.write_text("".join(f"{clave}={valor}\n" for clave, valor in valores.items()))
    return archivo


def env_minimo(directorio: Path, **extra: str) -> Path:
    valores = {"JWT_SECRET": "clave-de-prueba", "POSTGRES_PASSWORD": "pass-de-prueba"}
    valores.update(extra)
    return escribir_env(directorio, **valores)


def test_lee_los_valores_del_archivo_env(tmp_path):
    settings = cargar_settings(env_minimo(tmp_path, POSTGRES_DB="taller"))

    assert settings.postgres_db == "taller"


def test_el_entorno_tiene_prioridad_sobre_el_archivo_env(tmp_path, monkeypatch):
    archivo = env_minimo(tmp_path, SQL_ECHO="false")
    monkeypatch.setenv("SQL_ECHO", "true")

    assert cargar_settings(archivo).sql_echo is True


def test_sin_jwt_secret_no_arranca_y_nombra_la_variable(tmp_path):
    archivo = escribir_env(tmp_path, POSTGRES_PASSWORD="pass-de-prueba")

    with pytest.raises(ErrorConfiguracion) as error:
        cargar_settings(archivo)

    assert "JWT_SECRET" in str(error.value)


def test_sin_postgres_password_no_arranca_y_nombra_la_variable(tmp_path):
    archivo = escribir_env(tmp_path, JWT_SECRET="clave-de-prueba")

    with pytest.raises(ErrorConfiguracion) as error:
        cargar_settings(archivo)

    assert "POSTGRES_PASSWORD" in str(error.value)


def test_el_error_no_expone_el_valor_de_otros_secretos(tmp_path):
    archivo = escribir_env(tmp_path, POSTGRES_PASSWORD="contrasena-super-secreta")

    with pytest.raises(ErrorConfiguracion) as error:
        cargar_settings(archivo)

    assert "contrasena-super-secreta" not in str(error.value)


def test_los_secretos_no_aparecen_al_imprimir_la_configuracion(tmp_path):
    settings = cargar_settings(
        escribir_env(tmp_path, JWT_SECRET="clave-ultra-secreta", POSTGRES_PASSWORD="pass-ultra-secreta")
    )

    impreso = repr(settings) + str(settings)

    assert "clave-ultra-secreta" not in impreso
    assert "pass-ultra-secreta" not in impreso


def test_la_clave_de_firma_es_identica_en_dos_cargas(tmp_path):
    archivo = env_minimo(tmp_path)

    primera = cargar_settings(archivo).jwt_secret.get_secret_value()
    segunda = cargar_settings(archivo).jwt_secret.get_secret_value()

    assert primera == segunda == "clave-de-prueba"


def test_la_direccion_de_la_base_es_asincronica_y_se_arma_con_variables_sueltas(tmp_path):
    archivo = env_minimo(
        tmp_path,
        POSTGRES_USER="taller",
        POSTGRES_PASSWORD="x",
        POSTGRES_HOST="db",
        POSTGRES_PORT="5432",
        POSTGRES_DB="taller",
    )

    url = make_url(cargar_settings(archivo).url_base_datos)

    assert url.drivername == "postgresql+asyncpg"
    assert (url.host, url.port, url.database, url.username) == ("db", 5432, "taller", "taller")
    assert url.password == "x"


def test_la_direccion_escapa_caracteres_especiales_de_la_contrasena(tmp_path):
    archivo = env_minimo(tmp_path, POSTGRES_PASSWORD="p@ss:w/rd#1")

    url = make_url(cargar_settings(archivo).url_base_datos)

    assert url.password == "p@ss:w/rd#1"
    assert url.host == "localhost"


def test_valores_por_defecto_de_las_variables_no_sensibles(tmp_path):
    settings = cargar_settings(env_minimo(tmp_path))

    assert settings.postgres_user == "taller"
    assert settings.postgres_db == "taller"
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.postgres_test_db is None
    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_seconds == 1800
    assert settings.cookie_secure is False
    assert settings.bcrypt_rounds == 12
    assert settings.bcrypt_max_concurrency == 4
    assert settings.db_pool_size == 5
    assert settings.sql_echo is False


def test_un_puerto_no_numerico_impide_el_arranque_y_nombra_la_variable(tmp_path):
    archivo = env_minimo(tmp_path, POSTGRES_PORT="abc")

    with pytest.raises(ErrorConfiguracion) as error:
        cargar_settings(archivo)

    assert "POSTGRES_PORT" in str(error.value)


RAIZ = Path(__file__).resolve().parents[2]


def leer_env_example() -> dict[str, str]:
    valores = {}
    for linea in (RAIZ / "env.example").read_text().splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            clave, _, valor = linea.partition("=")
            valores[clave.strip()] = valor.strip()
    return valores


def test_env_example_tiene_todas_las_variables_de_la_configuracion():
    from app.core.config import Settings

    campos = {nombre.upper() for nombre in Settings.model_fields}

    assert set(leer_env_example()) == campos


def test_env_example_no_trae_secretos():
    valores = leer_env_example()

    assert valores["JWT_SECRET"] == ""
    assert valores["POSTGRES_PASSWORD"] == ""


@pytest.mark.parametrize("variable", ["JWT_SECRET", "POSTGRES_PASSWORD"])
def test_un_secreto_vacio_cuenta_como_faltante(tmp_path, variable):
    """env.example trae los secretos vacíos: copiarlo sin completarlo no debe dejar arrancar la app."""
    valores = {"JWT_SECRET": "clave-de-prueba", "POSTGRES_PASSWORD": "pass-de-prueba", variable: ""}

    with pytest.raises(ErrorConfiguracion) as error:
        cargar_settings(escribir_env(tmp_path, **valores))

    assert variable in str(error.value)
