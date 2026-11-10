"""HYG-04: issuing a token uses an aware UTC time, not the deprecated utcnow()."""
import os
import time
import warnings
from datetime import timedelta

import jwt

from src.api.auth import create_access_token


def decode(token):
    return jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])


def test_issuing_a_token_raises_no_deprecation_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        create_access_token({"sub": "bryan"})


def test_the_token_expires_in_fifteen_minutes_by_default():
    claims = decode(create_access_token({"sub": "bryan"}))
    assert abs(claims["exp"] - (time.time() + 15 * 60)) < 5


def test_a_custom_expiry_is_respected():
    claims = decode(create_access_token({"sub": "bryan"}, expires_delta=timedelta(hours=2)))
    assert abs(claims["exp"] - (time.time() + 2 * 3600)) < 5
