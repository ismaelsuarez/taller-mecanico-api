"""Configuración leída del entorno con pydantic-settings (EJ-1).

Los secretos (`JWT_SECRET`, `POSTGRES_PASSWORD`) no tienen valor por defecto: si faltan, la
aplicación no arranca. La clave de firma nunca se genera al arrancar (DD-20): si cambiara en
cada reinicio, todas las sesiones dejarían de valer.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ARCHIVO_ENV = Path(".env")


class ErrorConfiguracion(RuntimeError):
    """La configuración del entorno es incompleta o inválida."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ARCHIVO_ENV, env_file_encoding="utf-8", extra="ignore")

    postgres_user: str = "taller"
    postgres_password: SecretStr = Field(min_length=1)
    postgres_db: str = "taller"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_test_db: str | None = None

    jwt_secret: SecretStr = Field(min_length=1)
    jwt_algorithm: str = "HS256"
    access_token_expire_seconds: int = Field(default=1800, gt=0)
    cookie_secure: bool = False

    bcrypt_rounds: int = Field(default=12, ge=4, le=31)
    bcrypt_max_concurrency: int = Field(default=4, gt=0)
    db_pool_size: int = Field(default=5, gt=0)
    sql_echo: bool = False

    @computed_field(repr=False)
    @property
    def url_base_datos(self) -> str:
        """Dirección asincrónica de la base, armada con las variables sueltas."""
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
        return url.render_as_string(hide_password=False)


def cargar_settings(archivo_env: Path | None = ARCHIVO_ENV) -> Settings:
    """Lee la configuración; ante un error lista sólo los nombres de las variables, nunca sus valores."""
    try:
        return Settings(_env_file=archivo_env)
    except ValidationError as error:
        variables = sorted({str(detalle["loc"][0]).upper() for detalle in error.errors()})
        raise ErrorConfiguracion(
            "La configuración no es válida. Revisá estas variables de entorno (o el archivo .env): "
            + ", ".join(variables)
        ) from None


@lru_cache
def obtener_settings() -> Settings:
    """Configuración única de la aplicación; la llama el lifespan, nunca al importar."""
    return cargar_settings()
