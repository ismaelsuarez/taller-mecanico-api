"""Test de humo: la aplicación se importa sin efectos secundarios."""

from fastapi import FastAPI


def test_la_aplicacion_se_importa():
    from main import app

    assert isinstance(app, FastAPI)
