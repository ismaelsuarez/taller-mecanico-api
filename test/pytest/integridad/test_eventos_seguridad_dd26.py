"""Las siete acciones de `evento_seguridad` y sus actores contra DD-26 (EJ-7, design D7).

Caracterización (design D9): el código ya escribe lo que dice DD-26; no hubo RED previo. La prueba
recorre con la API real las siete acciones y compara la lista COMPLETA de eventos, en orden: un
evento de más (p. ej. un login común), uno de menos, otro actor u otra redacción la hacen fallar.
En «Rol X asignado a Y» / «revocado a Y», «Y» es el id numérico del usuario (SU-18, design D7).
"""

import secrets

import pytest

PASSWORD_NUEVA = secrets.token_hex(16)  # efímera: sólo para esta corrida


async def _eventos(entorno) -> list[tuple[str, str]]:
    return [(actor, accion) for actor, accion in await entorno.consulta(
        "SELECT actor, accion FROM evento_seguridad ORDER BY id",
    )]


async def _id_de(entorno, email: str) -> int:
    return (await entorno.consulta("SELECT id FROM usuario WHERE email = :email", email=email))[0][0]


@pytest.mark.asyncio
class TestAccionesDeEventoSeguridad:
    async def test_las_siete_acciones_y_sus_actores_coinciden_con_dd26(self, api_sembrada):
        from ordenes.conftest import _passwords_del_seed

        assert await _eventos(api_sembrada) == [("SISTEMA", "Carga de los datos iniciales")]  # 7. el seed

        async with api_sembrada.anonimo() as cliente:  # 1. registro: el actor es el correo del nuevo usuario
            registro = await cliente.post("/auth/registro", json={
                "email": "registro-dd26@example.com", "password": secrets.token_hex(16),
                "nombre": "Cliente DD26", "documento": "DD26-1", "telefono": "12345",
            })
        assert registro.status_code == 201, registro.text

        async with api_sembrada.entrar("admin@example.com") as admin:
            alta = await admin.post("/usuarios", json={  # 2. alta de personal: el actor es el admin
                "email": "personal-dd26@example.com", "nombre": "Personal DD26",
                "password_provisoria": secrets.token_hex(16), "rol": "MECANICO",
            })
            assert alta.status_code == 201, alta.text
            personal_id = alta.json()["id"]
            asignado = await admin.post(f"/usuarios/{personal_id}/roles", json={"rol": "RECEPCION"})  # 3
            assert asignado.status_code == 201, asignado.text
            revocado = await admin.delete(f"/usuarios/{personal_id}/roles/RECEPCION")  # 4
            assert revocado.status_code == 200, revocado.text

        async with api_sembrada.entrar("nuevo@example.com") as usuario:  # 5. cambio de contraseña: el actor es quien la cambia
            cambio = await usuario.post("/auth/cambiar-password", json={
                "password_actual": _passwords_del_seed()["nuevo@example.com"], "password_nueva": PASSWORD_NUEVA,
            })
        assert cambio.status_code == 200, cambio.text

        async with api_sembrada.anonimo() as cliente:  # 6. bloqueo: el actor es el correo intentado
            codigos = [
                (await cliente.post("/auth/login", json={
                    "email": "recepcion@example.com", "password": secrets.token_hex(16),
                })).status_code
                for _ in range(6)
            ]
        assert codigos == [401] * 5 + [429]

        # Los logins comunes (los de `entrar`) y los cinco 401 no dejan eventos: sólo estas siete filas.
        assert await _eventos(api_sembrada) == [
            ("SISTEMA", "Carga de los datos iniciales"),
            ("registro-dd26@example.com", "Alta de usuario cliente (registro)"),
            ("admin@example.com", "Alta de personal con rol MECANICO"),
            ("admin@example.com", f"Rol RECEPCION asignado a {personal_id}"),
            ("admin@example.com", f"Rol RECEPCION revocado a {personal_id}"),
            ("nuevo@example.com", "Cambio de contraseña"),
            ("recepcion@example.com", "Login bloqueado por demasiados intentos"),
        ]

    async def test_la_y_de_los_eventos_de_rol_es_el_id_del_usuario_afectado(self, api_sembrada):
        """Triangula: otro usuario y otro rol cambian la «Y»; el actor sigue siendo el admin que actúa."""
        cliente_id = await _id_de(api_sembrada, "cliente@example.com")
        async with api_sembrada.entrar("admin@example.com") as admin:
            assert (await admin.post(f"/usuarios/{cliente_id}/roles", json={"rol": "MECANICO"})).status_code == 201
            assert (await admin.delete(f"/usuarios/{cliente_id}/roles/MECANICO")).status_code == 200

        assert (await _eventos(api_sembrada))[1:] == [
            ("admin@example.com", f"Rol MECANICO asignado a {cliente_id}"),
            ("admin@example.com", f"Rol MECANICO revocado a {cliente_id}"),
        ]
