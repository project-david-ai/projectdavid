from __future__ import annotations

from unittest.mock import patch

import pytest
from projectdavid_common import ValidationInterface
from projectdavid_common.schemas.mcp_schemas import McpServerAuth

from projectdavid.clients.mcp_client import McpClient

validator = ValidationInterface()


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(
        self,
        path: str,
        *,
        json: dict[str, object],
    ):
        self.calls.append((path, json))

        class Response:
            status_code = 200
            text = ""

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict[str, object]:
                return {"placeholder": True}

        return Response()


def make_client() -> tuple[McpClient, RecordingClient]:
    recorder = RecordingClient()

    client = object.__new__(McpClient)
    client.client = recorder

    return client, recorder


def test_bearer_token_is_unwrapped_only_for_outbound_http() -> None:
    token = "sdk-super-secret"

    client, recorder = make_client()
    sentinel = object()

    with patch.object(
        validator.McpServerRegistrationRead,
        "model_validate",
        return_value=sentinel,
    ):
        result = client.create_server(
            name="private",
            url="https://example.test/mcp",
            bearer_token=token,
        )

    assert result is sentinel
    assert len(recorder.calls) == 1

    path, payload = recorder.calls[0]

    assert path == "/v1/mcp/servers"
    assert payload["auth"] == {
        "type": "bearer",
        "token": token,
    }

    request = validator.McpServerRegistrationCreate(
        name="private",
        url="https://example.test/mcp",
        auth=McpServerAuth(
            type="bearer",
            token=token,
        ),
    )

    assert token not in repr(request)
    assert token not in repr(request.auth)


def test_typed_bearer_auth_is_supported() -> None:
    client, recorder = make_client()
    sentinel = object()

    with patch.object(
        validator.McpServerRegistrationRead,
        "model_validate",
        return_value=sentinel,
    ):
        result = client.create_server(
            name="typed",
            url="https://example.test/mcp",
            auth=McpServerAuth(
                type="bearer",
                token="typed-secret",
            ),
        )

    assert result is sentinel

    _, payload = recorder.calls[0]

    assert payload["auth"] == {
        "type": "bearer",
        "token": "typed-secret",
    }


def test_public_registration_sends_none_auth() -> None:
    client, recorder = make_client()
    sentinel = object()

    with patch.object(
        validator.McpServerRegistrationRead,
        "model_validate",
        return_value=sentinel,
    ):
        result = client.create_server(
            name="public",
            url="https://example.test/mcp",
        )

    assert result is sentinel

    _, payload = recorder.calls[0]

    assert "auth" not in payload


def test_auth_and_bearer_token_are_mutually_exclusive() -> None:
    client, recorder = make_client()

    with pytest.raises(
        ValueError,
        match="either auth or bearer_token",
    ):
        client.create_server(
            name="invalid",
            url="https://example.test/mcp",
            auth=McpServerAuth(
                type="bearer",
                token="first",
            ),
            bearer_token="second",
        )

    assert recorder.calls == []


def test_blank_bearer_token_fails_before_http() -> None:
    client, recorder = make_client()

    with pytest.raises(ValueError):
        client.create_server(
            name="invalid",
            url="https://example.test/mcp",
            bearer_token="   ",
        )

    assert recorder.calls == []


def test_read_contract_exposes_auth_type_but_not_credentials() -> None:
    fields = validator.McpServerRegistrationRead.model_fields

    assert "auth_type" in fields
    assert "token" not in fields
    assert "credential_id" not in fields
    assert "encrypted_payload" not in fields


def test_secretstr_default_dump_is_not_used_for_http() -> None:
    token = "real-secret"

    request = validator.McpServerRegistrationCreate(
        name="private",
        url="https://example.test/mcp",
        auth=McpServerAuth(
            type="bearer",
            token=token,
        ),
    )

    ordinary = request.model_dump(mode="json")
    outbound = McpClient._registration_create_payload(request)

    assert ordinary["auth"]["token"] != token
    assert outbound["auth"]["token"] == token
