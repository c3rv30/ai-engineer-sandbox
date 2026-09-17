"""Regresión de la firma del tenant (SEC-05), en el lado de la aplicación.

La comparación con el HMAC que calcula Postgres está en tests/db/.
"""
import hashlib
import hmac
import os

from src.services.db import sign_tenant

TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_firma_es_hmac_sha256_del_tenant_con_la_clave():
    esperada = hmac.new(os.environ["TENANT_SIGNING_KEY"].encode(), TENANT.encode(), hashlib.sha256).hexdigest()
    assert sign_tenant(TENANT) == esperada


def test_firmas_distintas_para_tenants_distintos():
    assert sign_tenant(TENANT) != sign_tenant("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
