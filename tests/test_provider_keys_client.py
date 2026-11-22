"""HTTP contracts for the SDK BYOK management client."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest
from projectdavid_common import ValidationInterface
from pydantic import ValidationError

from projectdavid.clients.provider_keys_client import ProviderKeysClient
from projectdavid.entity import Entity

validator = ValidationInterface()


@pytest.fixture()
def provider_record() -> dict:
    return {
        "id": "pkey_test",
        "owner_id": "user_test",
        "provider": "hyperbolic",
        "name": "Primary",
        "created_at": "2026-11-22T12:30:00",
        "revoked_at": None,
    }


def _client(status_code: int, response_data=None):
    captured = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if status_code == 204:
            return httpx.Response(status_code)
        return httpx.Response(status_code, json=response_data)

    # Bypass transport creation in BaseAPIClient; requests go through the
    # same .client interface used by every existing SDK resource client.
    service = ProviderKeysClient.__new__(ProviderKeysClient)
    service.client = httpx.Client(
        base_url="https://core.example.test",
        headers={"X-API-Key": "sk_test"},
        transport=httpx.MockTransport(handle),
    )
    return service, captured


def test_create_unwraps_secret_only_on_wire_and_returns_model(provider_record):
    service, requests = _client(201, provider_record)
    try:
        result = service.create(
            provider=" Hyperbolic ",
            api_key="secret-on-the-wire",
            name=" Primary ",
        )
    finally:
        service.client.close()

    assert type(result) is validator.ProviderKeyRead
    assert result.created_at == datetime(2026, 11, 22, 12, 30)
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/provider-keys"
    assert requests[0].headers["X-API-Key"] == "sk_test"
    assert json.loads(requests[0].content) == {
        "provider": "hyperbolic",
        "name": "Primary",
        "api_key": "secret-on-the-wire",
    }
    assert "secret-on-the-wire" not in result.model_dump_json()
    assert not hasattr(result, "credential_id")
    assert not hasattr(result, "fingerprint")


def test_create_existing_registration_accepts_200(provider_record):
    service, requests = _client(200, provider_record)
    try:
        result = service.create(provider="hyperbolic", api_key="another-secret")
    finally:
        service.client.close()
    assert result.id == "pkey_test"
    assert len(requests) == 1


def test_list_returns_pydantic_models(provider_record):
    revoked = dict(provider_record, id="pkey_revoked", revoked_at="2026-11-22T13:00:00")
    service, requests = _client(200, [provider_record, revoked])
    try:
        result = service.list()
    finally:
        service.client.close()
    assert [row.id for row in result] == ["pkey_test", "pkey_revoked"]
    assert all(isinstance(row, validator.ProviderKeyRead) for row in result)
    assert result[1].revoked_at == datetime(2026, 11, 22, 13, 0)
    assert requests[0].url.path == "/v1/provider-keys"


def test_list_empty_returns_empty_list():
    service, _ = _client(200, [])
    try:
        assert service.list() == []
    finally:
        service.client.close()


def test_retrieve_returns_model(provider_record):
    service, requests = _client(200, provider_record)
    try:
        result = service.retrieve("pkey_test")
    finally:
        service.client.close()
    assert isinstance(result, validator.ProviderKeyRead)
    assert result.id == "pkey_test"
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/provider-keys/pkey_test"


def test_update_validates_and_returns_model(provider_record):
    updated = dict(provider_record, name="Renamed")
    service, requests = _client(200, updated)
    try:
        result = service.update("pkey_test", name=" Renamed ")
    finally:
        service.client.close()
    assert isinstance(result, validator.ProviderKeyRead)
    assert result.name == "Renamed"
    assert requests[0].method == "PATCH"
    assert requests[0].url.path == "/v1/provider-keys/pkey_test"
    assert json.loads(requests[0].content) == {"name": "Renamed"}


def test_revoke_expects_no_body():
    service, requests = _client(204)
    try:
        assert service.revoke("pkey_test") is None
    finally:
        service.client.close()
    assert requests[0].method == "DELETE"
    assert requests[0].url.path == "/v1/provider-keys/pkey_test"


@pytest.mark.parametrize("status_code", [401, 404, 503])
def test_http_errors_propagate_without_swallowing(status_code):
    service, _ = _client(status_code, {"detail": "Unavailable"})
    try:
        with pytest.raises(httpx.HTTPStatusError) as exc:
            service.retrieve("pkey_test")
    finally:
        service.client.close()
    assert exc.value.response.status_code == status_code


@pytest.mark.parametrize(
    ("provider", "api_key"),
    [("INVALID PROVIDER", "secret"), ("hyperbolic", "  ")],
)
def test_create_invalid_request_never_reaches_wire(provider, api_key):
    service, requests = _client(201, None)
    try:
        with pytest.raises(ValidationError):
            service.create(provider=provider, api_key=api_key)
    finally:
        service.client.close()
    assert not requests


def test_update_invalid_name_never_reaches_wire():
    service, requests = _client(200, None)
    try:
        with pytest.raises(ValidationError):
            service.update("pkey_test", name=" ")
    finally:
        service.client.close()
    assert not requests


def test_entity_exposes_lazy_provider_keys_client():
    entity = Entity(base_url="https://core.example.test", api_key="sk_test")
    assert entity._provider_keys_client is None
    client = entity.provider_keys
    assert isinstance(client, ProviderKeysClient)
    assert client is entity.provider_keys
    assert client.base_url == entity.base_url
    if hasattr(client.client, "close"):
        client.client.close()
