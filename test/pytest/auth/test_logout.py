"""Logout público: sólo elimina la cookie, no revoca JWT copiados ni escribe."""

from http.cookies import SimpleCookie

import pytest

from .test_registro import estado_guardado


@pytest.mark.parametrize("segura", [False, True])
@pytest.mark.parametrize("sesion", ["valida", "ausente", "invalida"])
async def test_logout_elimina_cookie_sin_revocar_ni_escribir(
    api_auth, aplicacion_auth, crear_usuario_auth, segura, sesion,
):
    aplicacion_auth.state.settings.cookie_secure = segura
    api_auth.base_url = "https://test" if segura else "http://test"
    usuario, password = await crear_usuario_auth(email="logout@example.com")
    login = await api_auth.post("/auth/login", json={"email": usuario.email, "password": password})
    assert login.status_code == 200
    emitida = SimpleCookie(login.headers["set-cookie"])["access_token"]
    if sesion != "valida":
        api_auth.cookies.clear()
    encabezados = {"Cookie": "access_token=sesion-invalida"} if sesion == "invalida" else {}
    antes = await estado_guardado(aplicacion_auth)
    respuesta = await api_auth.post("/auth/logout", headers=encabezados)
    assert respuesta.status_code == 200
    assert respuesta.json() == {"mensaje": "Sesión cerrada"}
    assert respuesta.headers["content-type"] == "application/json"
    assert "retry-after" not in respuesta.headers
    assert len(respuesta.headers.get_list("set-cookie")) == 1
    eliminada = SimpleCookie(respuesta.headers["set-cookie"])["access_token"]
    assert eliminada.value == "" and eliminada["max-age"] == "0" and eliminada["expires"]
    for atributo in ("path", "domain", "secure", "httponly", "samesite"):
        assert eliminada[atributo] == emitida[atributo]
    # Sin cookie explícita: el cliente debe aceptar la eliminación de la emitida.
    yo = await api_auth.get("/auth/yo")
    assert yo.status_code == 401
    assert yo.json() == {"detail": "La sesión no es válida. Volvé a iniciar sesión."}
    assert "set-cookie" not in yo.headers
    copiada = await api_auth.get("/auth/yo", headers={"Cookie": f"access_token={emitida.value}"})
    assert copiada.status_code == 200 and copiada.json()["usuario"]["id"] == usuario.id
    assert "set-cookie" not in copiada.headers
    assert await estado_guardado(aplicacion_auth) == antes
