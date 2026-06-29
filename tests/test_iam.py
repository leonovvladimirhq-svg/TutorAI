"""Юнит-тест сборки JWT из ключа сервисного аккаунта (без сети)."""
from __future__ import annotations

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.iam import IAM_TOKEN_URL, build_jwt


def _make_sa_key() -> tuple[dict, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    key = {
        "id": "test-key-id",
        "service_account_id": "test-sa-id",
        # имитируем служебную строку Yandex перед PEM
        "private_key": "PLEASE DO NOT REMOVE THIS LINE! Yandex.Cloud SA Key ID <x>\n" + pem,
    }
    return key, public_pem


def test_build_jwt_header_and_signature():
    key, public_pem = _make_sa_key()
    token = build_jwt(key)

    header = jwt.get_unverified_header(token)
    assert header["alg"] == "PS256"
    assert header["kid"] == "test-key-id"

    payload = jwt.decode(token, public_pem, algorithms=["PS256"], audience=IAM_TOKEN_URL)
    assert payload["iss"] == "test-sa-id"
    assert payload["aud"] == IAM_TOKEN_URL
    assert payload["exp"] > payload["iat"]
