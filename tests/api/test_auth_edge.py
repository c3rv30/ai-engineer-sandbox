"""Regression of authentication at the edge (SEC-01, SEC-02).

SEC-01: the JWT key was hardcoded and committed, so anyone could sign tokens for any
tenant. SEC-02: the token's `tenant_id` travelled unvalidated all the way to
`SET app.current_tenant`.
"""
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import jwt
import pytest

from tests.api.doubles import generator_script

REPO = Path(__file__).resolve().parents[2]
ENDPOINTS = [
    ("/chat/", {"query": "Where did he work?"}),
    ("/chat/stream/", {"query": "Where did he work?"}),
]


def test_token_signed_with_another_key(api):
    api.script(generator_script("should not get here"))
    other = "0" * 64
    assert other != os.environ["JWT_SECRET_KEY"]
    r = api.client.post("/chat/", json={"query": "Where did he work?"}, headers=api.header(key=other))
    assert r.status_code == 401
    assert api.graph.invocations == []


@pytest.mark.parametrize("field", ["no_sub", "no_tenant"])
def test_token_without_user_or_tenant(api, field):
    api.script(generator_script("should not get here"))
    r = api.client.post("/chat/", json={"query": "Where did he work?"}, headers=api.header(**{field: True}))
    assert r.status_code == 401
    assert api.graph.invocations == []


@pytest.mark.parametrize("tenant", [
    "not-a-uuid",
    "'; SELECT set_config('app.current_tenant', '11111111-1111-1111-1111-111111111111', false); --",
    "11111111-1111-1111-1111-11111111111",   # one digit short
    "",
    12345,
])
def test_malformed_tenant_in_the_token(api, tenant):
    api.script(generator_script("should not get here"))
    payload = {"sub": "bryan", "tenant_id": tenant, "exp": datetime.utcnow() + timedelta(minutes=5)}
    token = jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")
    r = api.client.post("/chat/", json={"query": "Where did he work?"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, r.text
    # Not a 500 downstream, and the value does not reach the data layer.
    assert api.graph.invocations == []


@pytest.mark.parametrize("path, body", ENDPOINTS)
def test_request_without_token(api, path, body):
    r = api.client.post(path, json=body)
    assert r.status_code == 401
    assert api.graph.invocations == []


def test_ingestion_without_token(api):
    r = api.client.post("/ingest/", files={"file": ("cv.md", b"content", "text/markdown")})
    assert r.status_code == 401
    assert api.record.ingestions == []


def test_positive_control_with_the_token_endpoint(api):
    """A token issued by the real API gets in and reaches the graph with its tenant typed."""
    api.script(generator_script("He worked at Betterfly."))
    token = api.client.post("/auth/token", data={"username": "bryan", "password": "password123"}).json()["access_token"]
    r = api.client.post("/chat/", json={"query": "Where did he work?"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert len(api.graph.invocations) == 1
    tenant = api.graph.invocations[0]["tenant_id"]
    assert isinstance(tenant, uuid.UUID)
    assert tenant == uuid.UUID("00000000-0000-0000-0000-000000000000")


def test_wrong_credentials_get_no_token(api):
    r = api.client.post("/auth/token", data={"username": "bryan", "password": "wrong"})
    assert r.status_code == 401


# --- SEC-01: the signing key is required at startup ---

def _import_auth(key):
    env = {**os.environ, "JWT_SECRET_KEY": key}
    return subprocess.run([sys.executable, "-c", "import src.api.auth"], cwd=REPO,
                          env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("key, expected", [
    ("", "JWT_SECRET_KEY is not set"),
    ("short", "too short"),
])
def test_the_api_does_not_start_without_a_usable_key(key, expected):
    result = _import_auth(key)
    assert result.returncode != 0
    assert expected in result.stderr
    assert "RuntimeError" in result.stderr


def test_with_a_valid_key_the_module_imports():
    assert _import_auth("a" * 32).returncode == 0
