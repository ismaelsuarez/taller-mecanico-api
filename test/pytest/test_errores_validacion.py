"""S3: los rechazos HTTP explican cómo corregir la entrada sin exponerla."""

import pytest
from conftest import cliente_http
from fastapi import FastAPI
from httpx import Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlmodel import col, select

from app.core.errores import registrar_traductores
from app.modules.clientes.models import Cliente

CLIENTE = {"nombre": "Cliente de prueba", "documento": "DNI-80001", "telefono": "11-1234"}
VEHICULO = {"patente": "AA123BB", "marca": "Fiat", "modelo": "Cronos", "anio": 2020}
REPUESTO = {"codigo": "VAL-01", "descripcion": "Filtro", "precio": "10.00", "stock_inicial": 2}
MENSAJE_GENERICO = "Revisá los datos enviados: hay un valor no válido."
EXTRAS = "Enviá sólo los datos permitidos para esta operación."


@pytest.fixture
async def escenario(api):
    cliente, motor = api
    creado = await cliente.post("/clientes", json=CLIENTE)
    assert creado.status_code == 201
    repuesto = await cliente.post("/repuestos", json=REPUESTO)
    assert repuesto.status_code == 201
    ruta_cliente = f"/clientes/{creado.json()['id']}"
    ruta_repuesto = f"/repuestos/{repuesto.json()['id']}"
    cambiado = await cliente.patch(ruta_repuesto, json={"precio": "11.00"})
    assert cambiado.status_code == 200

    async def estado_guardado() -> list:
        # No hay listado HTTP de clientes todavía; comprobamos también altas fantasma.
        async with motor.connect() as conexion:
            consulta = select(
                Cliente.id, Cliente.nombre, Cliente.documento, Cliente.telefono
            ).order_by(col(Cliente.id))
            clientes = (await conexion.execute(consulta)).all()
        respuestas = []
        for ruta in (
            ruta_cliente, "/repuestos", ruta_repuesto + "/movimientos",
            ruta_repuesto + "/precios",
        ):
            respuesta = await cliente.get(ruta)
            assert respuesta.status_code == 200
            respuestas.append(respuesta.json())
        return [clientes, *respuestas]

    return cliente, ruta_cliente, ruta_repuesto, estado_guardado


def _verificar_rechazo(respuesta: Response, mensajes: list[str]) -> None:
    assert respuesta.status_code == 422
    # La igualdad exacta impide filtrar input, loc, type, ctx o texto interno.
    assert respuesta.json() == {"detail": [{"msg": mensaje} for mensaje in mensajes]}


async def test_openapi_documenta_422_humano_sin_alterar_salud(api):
    cliente, _ = api
    respuesta = await cliente.get("/openapi.json")
    assert respuesta.status_code == 200
    documento = respuesta.json()

    def resolver(esquema: dict) -> dict:
        if "$ref" in esquema:
            return documento["components"]["schemas"][esquema["$ref"].rsplit("/", 1)[1]]
        return esquema

    for ruta, codigos in (("/health/live", {"200"}), ("/health/ready", {"200", "503"})):
        respuestas = documento["paths"][ruta]["get"]["responses"]
        assert set(respuestas) == codigos
        assert respuestas["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/EstadoSalud"
        }
    no_listo = documento["paths"]["/health/ready"]["get"]["responses"]["503"]
    assert no_listo["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EstadoNoListo"
    }

    for ruta, operaciones in documento["paths"].items():
        if not ruta.startswith(("/clientes", "/vehiculos", "/repuestos")):
            continue
        for operacion in operaciones.values():
            contenido = operacion["responses"]["422"]["content"]["application/json"]
            error = resolver(contenido["schema"])
            detalle = error["properties"]["detail"]
            variantes = detalle.get("anyOf", [detalle])
            assert {variante["type"] for variante in variantes} == {"array", "string"}
            assert set(error["properties"]) == {"detail"}
            assert error["required"] == ["detail"]
            assert error["additionalProperties"] is False
            lista = next(variante for variante in variantes if variante["type"] == "array")
            mensaje = resolver(lista["items"])
            # No se documentan loc, type, input, ctx ni otros detalles técnicos.
            assert set(mensaje["properties"]) == {"msg"}
            assert mensaje["properties"]["msg"]["type"] == "string"
            assert mensaje["required"] == ["msg"]
            assert mensaje["additionalProperties"] is False


async def test_ruta_invalida_devuelve_mensaje_humano(api):
    cliente, _ = api
    respuesta = await cliente.get("/clientes/abc")
    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "detail": [{"msg": "Ingresá un número entero para el cliente seleccionado."}]
    }


@pytest.mark.parametrize(("metodo", "ruta", "opciones", "mensajes"), [
    ("POST", "/clientes", {"json": {"nombre": "Dato privado"}},
     ["Completá el documento.", "Completá el teléfono."]),
    ("POST", "/clientes", {}, ["Completá los datos de la solicitud."]),
    ("POST", "/clientes", {"content": '{"nombre":"Dato privado",',
     "headers": {"Content-Type": "application/json"}},
     ["No pudimos leer los datos enviados. Revisá el formato y volvé a intentar."]),
    ("POST", "/clientes", {"json": []}, [MENSAJE_GENERICO]),
    ("POST", "/clientes", {"json": CLIENTE | {"nombre": 123}}, ["Ingresá texto para el nombre."]),
    ("POST", "/clientes", {"json": CLIENTE | {"nombre": None}}, ["Ingresá texto para el nombre."]),
    ("POST", "/clientes", {"json": CLIENTE | {"nombre": ""}},
     ["Completá el nombre con un texto más largo."]),
    ("POST", "/clientes", {"json": CLIENTE | {"documento": "x" * 51}},
     ["Usá un texto más corto para el documento."]),
    ("POST", "/clientes", {"json": CLIENTE | {"dato_privado": "NO_REPETIR"}}, [EXTRAS]),
    ("POST", "{cliente}/vehiculos", {"json": VEHICULO | {"anio": 1949}},
     ["Revisá el año: está fuera del rango permitido."]),
    ("POST", "{cliente}/vehiculos", {"json": VEHICULO | {"anio": 2101}},
     ["Revisá el año: está fuera del rango permitido."]),
    ("POST", "{cliente}/vehiculos", {"json": VEHICULO | {"anio": 2020.5}},
     ["Ingresá un número entero para el año."]),
    ("GET", "/repuestos?page=privado", {}, ["Ingresá un número entero para la página."]),
    ("GET", "/repuestos?size=privado", {}, ["Ingresá un número entero para la cantidad por página."]),
    ("GET", "/repuestos?page=0", {}, ["Revisá la página: está fuera del rango permitido."]),
    ("GET", "/repuestos?size=101", {}, ["Revisá la cantidad por página: está fuera del rango permitido."]),
    ("GET", "/repuestos?dato_privado=NO_REPETIR", {}, [EXTRAS]),
    ("GET", "/repuestos/privado", {}, ["Ingresá un número entero para el repuesto seleccionado."]),
    ("DELETE", "/vehiculos/privado", {}, ["Ingresá un número entero para el vehículo seleccionado."]),
    ("POST", "/repuestos", {"json": REPUESTO | {"stock_inicial": -1}},
     ["Revisá la cantidad inicial: está fuera del rango permitido."]),
    ("POST", "{repuesto}/reponer", {"json": {"cantidad": []}},
     ["Ingresá un número entero para la cantidad."]),
    ("POST", "{repuesto}/reponer", {"json": {"cantidad": 0}},
     ["Revisá la cantidad: está fuera del rango permitido."]),
    ("PATCH", "{repuesto}", {"json": {"descripcion": None}}, [MENSAJE_GENERICO]),
    ("PATCH", "{repuesto}", {"json": {"precio": None}}, [MENSAJE_GENERICO]),
    ("PATCH", "{repuesto}", {"json": {"stock": 100}}, [EXTRAS]),
])
async def test_validacion_no_expone_entrada_ni_cambia_datos(
    escenario, metodo, ruta, opciones, mensajes
):
    cliente, ruta_cliente, ruta_repuesto, estado_guardado = escenario
    antes = await estado_guardado()
    respuesta = await cliente.request(
        metodo, ruta.format(cliente=ruta_cliente, repuesto=ruta_repuesto), **opciones
    )
    _verificar_rechazo(respuesta, mensajes)
    assert await estado_guardado() == antes


@pytest.mark.parametrize(("precio", "mensaje"), [
    ("no-es-un-importe", "Ingresá un importe válido para el precio."),
    ([], "Ingresá un importe válido para el precio."),
    ("NaN", "Ingresá un importe válido para el precio."),
    ("Infinity", "Ingresá un importe válido para el precio."),
    ("-Infinity", "Ingresá un importe válido para el precio."),
    ("0", "Revisá el precio: está fuera del rango permitido."),
    ("-0.01", "Revisá el precio: está fuera del rango permitido."),
    ("0.001", "Revisá el precio: el importe tiene demasiados dígitos o decimales."),
    ("100000000", "Revisá el precio: el importe tiene demasiados dígitos o decimales."),
    ("123456789.12", "Revisá el precio: el importe tiene demasiados dígitos o decimales."),
])
async def test_importes_invalidos_no_cambian_precio_ni_historial(escenario, precio, mensaje):
    cliente, _, ruta_repuesto, estado_guardado = escenario
    antes = await estado_guardado()
    respuesta = await cliente.patch(ruta_repuesto, json={"precio": precio})
    _verificar_rechazo(respuesta, [mensaje])
    assert await estado_guardado() == antes


class EntradaDePrueba(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dato_interno: int
    nombre: str = "Correcto"

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, valor: str) -> str:
        if valor == "NO_REPETIR":
            raise ValueError(f"Error interno de tabla_privada: {valor}")
        return valor


@pytest.mark.parametrize("cuerpo", [
    {}, {"dato_interno": "NO_REPETIR"}, {"dato_interno": 1, "nombre": "NO_REPETIR"},
])
async def test_campo_o_validador_desconocido_tiene_respuesta_segura(cuerpo):
    # Una ruta aislada ejercita futuras validaciones sin agregar endpoints a la API.
    app = FastAPI()
    registrar_traductores(app)

    @app.post("/validar")
    async def validar(datos: EntradaDePrueba) -> dict:
        return datos.model_dump()

    async with cliente_http(app) as cliente:
        respuesta = await cliente.post("/validar", json=cuerpo)
    _verificar_rechazo(respuesta, [MENSAJE_GENERICO])


@pytest.mark.parametrize(("metodo", "ruta", "opciones", "codigo", "mensaje"), [
    ("GET", "/clientes/999999", {}, 404, "Cliente no encontrado."),
    ("GET", "/repuestos/999999", {}, 404, "Repuesto no encontrado."),
    ("DELETE", "/vehiculos/999999", {}, 404, "Vehículo no encontrado."),
    ("POST", "/clientes", {"json": CLIENTE}, 409, "Ya existe un cliente con ese documento."),
    ("POST", "/repuestos", {"json": REPUESTO}, 409, "Ya existe un repuesto con ese código."),
    ("GET", "/repuestos?page=2", {}, 422, "La página 2 no existe: hay 1"),
])
async def test_errores_de_dominio_conservan_su_cuerpo(
    escenario, metodo, ruta, opciones, codigo, mensaje
):
    cliente, _, _, estado_guardado = escenario
    antes = await estado_guardado()
    respuesta = await cliente.request(metodo, ruta, **opciones)
    assert respuesta.status_code == codigo
    assert respuesta.json() == {"detail": mensaje}
    assert await estado_guardado() == antes


@pytest.mark.parametrize("anio", [1950, 2100])
async def test_limites_validos_y_patch_omitido_siguen_funcionando(escenario, anio):
    cliente, ruta_cliente, ruta_repuesto, estado_guardado = escenario
    respuesta = await cliente.post(ruta_cliente + "/vehiculos", json=VEHICULO | {"anio": anio})
    assert respuesta.status_code == 201
    vehiculo = respuesta.json()
    assert vehiculo == VEHICULO | {
        "anio": anio, "id": vehiculo["id"], "cliente_id": int(ruta_cliente.rsplit("/", 1)[1])
    }
    antes = await estado_guardado()
    respuesta = await cliente.patch(ruta_repuesto, json={})
    assert respuesta.status_code == 200
    assert respuesta.json()["precio"] == "11.00"
    assert await estado_guardado() == antes
