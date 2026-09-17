"""Regresión de la autenticación en el borde (SEC-01, SEC-02).

SEC-01: la clave del JWT estaba hardcodeada y versionada, así que cualquiera podía
firmar tokens para cualquier tenant. SEC-02: el `tenant_id` del token viajaba sin
validar hasta `SET app.current_tenant`.
"""
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import jwt
import pytest

from tests.api.dobles import guion_redactor

REPO = Path(__file__).resolve().parents[2]
ENDPOINTS = [
    ("/chat/", {"query": "¿Dónde trabajó?"}),
    ("/chat/stream/", {"query": "¿Dónde trabajó?"}),
]


def test_token_firmado_con_otra_clave(api):
    api.guion(guion_redactor("no debería llegar aquí"))
    otra = "0" * 64
    assert otra != os.environ["JWT_SECRET_KEY"]
    r = api.client.post("/chat/", json={"query": "¿Dónde trabajó?"}, headers=api.cabecera(clave=otra))
    assert r.status_code == 401
    assert api.grafo.invocaciones == []


@pytest.mark.parametrize("campo", ["sin_sub", "sin_tenant"])
def test_token_sin_usuario_o_sin_tenant(api, campo):
    api.guion(guion_redactor("no debería llegar aquí"))
    r = api.client.post("/chat/", json={"query": "¿Dónde trabajó?"}, headers=api.cabecera(**{campo: True}))
    assert r.status_code == 401
    assert api.grafo.invocaciones == []


@pytest.mark.parametrize("tenant", [
    "no-es-un-uuid",
    "'; SELECT set_config('app.current_tenant', '11111111-1111-1111-1111-111111111111', false); --",
    "11111111-1111-1111-1111-11111111111",   # un dígito de menos
    "",
    12345,
])
def test_tenant_malformado_en_el_token(api, tenant):
    api.guion(guion_redactor("no debería llegar aquí"))
    payload = {"sub": "bryan", "tenant_id": tenant, "exp": datetime.utcnow() + timedelta(minutes=5)}
    token = jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
    r = api.client.post("/chat/", json={"query": "¿Dónde trabajó?"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, r.text
    # No es un 500 aguas abajo y el valor no llega a la capa de datos.
    assert api.grafo.invocaciones == []


@pytest.mark.parametrize("ruta, cuerpo", ENDPOINTS)
def test_peticion_sin_token(api, ruta, cuerpo):
    r = api.client.post(ruta, json=cuerpo)
    assert r.status_code == 401
    assert api.grafo.invocaciones == []


def test_ingesta_sin_token(api):
    r = api.client.post("/ingest/", files={"file": ("cv.md", b"contenido", "text/markdown")})
    assert r.status_code == 401
    assert api.registro.ingestas == []


def test_control_positivo_con_el_endpoint_de_token(api):
    """Un token emitido por la API real entra y llega al grafo con su tenant tipado."""
    api.guion(guion_redactor("Trabajó en Betterfly."))
    token = api.client.post("/auth/token", data={"username": "bryan", "password": "password123"}).json()["access_token"]
    r = api.client.post("/chat/", json={"query": "¿Dónde trabajó?"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert len(api.grafo.invocaciones) == 1
    tenant = api.grafo.invocaciones[0]["tenant_id"]
    assert isinstance(tenant, uuid.UUID)
    assert tenant == uuid.UUID("00000000-0000-0000-0000-000000000000")


def test_credenciales_incorrectas_no_dan_token(api):
    r = api.client.post("/auth/token", data={"username": "bryan", "password": "otra"})
    assert r.status_code == 401


# --- SEC-01: la clave de firma es obligatoria al arrancar ---

def _importar_auth(clave):
    entorno = {**os.environ, "JWT_SECRET_KEY": clave}
    return subprocess.run([sys.executable, "-c", "import src.api.auth"], cwd=REPO,
                          env=entorno, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("clave, esperado", [
    ("", "JWT_SECRET_KEY no está configurada"),
    ("corta", "demasiado corta"),
])
def test_la_api_no_arranca_sin_clave_utilizable(clave, esperado):
    resultado = _importar_auth(clave)
    assert resultado.returncode != 0
    assert esperado in resultado.stderr
    assert "RuntimeError" in resultado.stderr


def test_con_una_clave_valida_el_modulo_importa():
    assert _importar_auth("a" * 32).returncode == 0
