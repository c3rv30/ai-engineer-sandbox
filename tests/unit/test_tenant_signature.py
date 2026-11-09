"""Regression of the tenant signature (SEC-05), on the application side.

The comparison with the HMAC Postgres computes is in tests/db/.
"""
import hashlib
import hmac
import os

from src.services.db import sign_tenant

TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_signature_is_the_hmac_sha256_of_the_tenant_with_the_key():
    expected = hmac.new(os.environ["TENANT_SIGNING_KEY"].encode(), TENANT.encode(), hashlib.sha256).hexdigest()
    assert sign_tenant(TENANT) == expected


def test_different_signatures_for_different_tenants():
    assert sign_tenant(TENANT) != sign_tenant("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
