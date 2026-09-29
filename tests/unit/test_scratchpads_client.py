from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import httpx
import pytest
from projectdavid_common import ValidationInterface

from projectdavid.clients.scratchpads_client import ScratchpadsClient
from projectdavid.entity import Entity

validator = ValidationInterface()


def _resource() -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()

    return {
        "id": "scratchpad_1",
        "owner_id": "user_1",
        "thread_id": "thread_1",
        "created_at": now,
        "updated_at": now,
        "meta_data": {},
    }


def _client(handler) -> ScratchpadsClient:
    client = ScratchpadsClient(
        base_url="http://test",
        api_key="test-key",
    )

    client.client.close()

    client.client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
        headers={
            "X-API-Key": "test-key",
        },
    )

    return client


def test_entity_exposes_lazy_scratchpads_client() -> None:
    entity = Entity(
        base_url="http://test",
        api_key="test-key",
    )

    first = entity.scratchpads
    second = entity.scratchpads

    assert isinstance(
        first,
        ScratchpadsClient,
    )

    assert first is second


def test_resource_plane_contract() -> None:
    calls = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        calls.append(
            (
                request.method,
                request.url.path,
            )
        )

        if request.method == "GET" and request.url.path == "/v1/scratchpads":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [_resource()],
                },
            )

        if request.method == "DELETE":
            return httpx.Response(
                200,
                json={
                    "id": "scratchpad_1",
                    "object": "scratchpad.deleted",
                    "deleted": True,
                },
            )

        return httpx.Response(
            200,
            json=_resource(),
        )

    client = _client(handler)

    assert isinstance(
        client.create_scratchpad("thread_1"),
        validator.ScratchpadRead,
    )

    assert isinstance(
        client.retrieve_scratchpad("scratchpad_1"),
        validator.ScratchpadRead,
    )

    assert isinstance(
        client.retrieve_scratchpad_by_thread("thread_1"),
        validator.ScratchpadRead,
    )

    assert isinstance(
        client.list_scratchpads(),
        validator.ScratchpadList,
    )

    assert isinstance(
        client.update_scratchpad(
            "scratchpad_1",
            meta_data={
                "purpose": "research",
            },
        ),
        validator.ScratchpadRead,
    )

    assert isinstance(
        client.delete_scratchpad("scratchpad_1"),
        validator.ScratchpadDeleted,
    )

    assert calls == [
        (
            "POST",
            "/v1/scratchpads",
        ),
        (
            "GET",
            "/v1/scratchpads/scratchpad_1",
        ),
        (
            "GET",
            "/v1/threads/thread_1/scratchpad",
        ),
        (
            "GET",
            "/v1/scratchpads",
        ),
        (
            "PATCH",
            "/v1/scratchpads/scratchpad_1",
        ),
        (
            "DELETE",
            "/v1/scratchpads/scratchpad_1",
        ),
    ]


def test_content_plane_contract() -> None:
    calls = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        calls.append(
            (
                request.method,
                request.url.path,
            )
        )

        if request.method == "DELETE":
            return httpx.Response(
                200,
                json={
                    "id": "scratchpad_1",
                    "object": "scratchpad.state.cleared",
                    "scope": "content",
                    "cleared": True,
                },
            )

        return httpx.Response(
            200,
            json={
                "scratchpad_id": "scratchpad_1",
                "content": ("NEW PLAN" if request.method == "PUT" else "PLAN"),
                "updated_at": None,
            },
        )

    client = _client(handler)

    read = client.get_content("scratchpad_1")

    written = client.set_content(
        "scratchpad_1",
        "NEW PLAN",
    )

    cleared = client.clear_content("scratchpad_1")

    assert isinstance(
        read,
        validator.ScratchpadContentRead,
    )

    assert written.content == "NEW PLAN"
    assert cleared.scope == "content"

    assert calls == [
        (
            "GET",
            "/v1/scratchpads/scratchpad_1/content",
        ),
        (
            "PUT",
            "/v1/scratchpads/scratchpad_1/content",
        ),
        (
            "DELETE",
            "/v1/scratchpads/scratchpad_1/content",
        ),
    ]


def test_entry_plane_contract() -> None:
    calls = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        calls.append(
            (
                request.method,
                request.url.path,
            )
        )

        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "scratchpad_id": "scratchpad_1",
                    "content": "finding",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "scratchpad_id": "scratchpad_1",
                            "content": "finding",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ],
                },
            )

        return httpx.Response(
            200,
            json={
                "id": "scratchpad_1",
                "object": "scratchpad.state.cleared",
                "scope": "entries",
                "cleared": True,
            },
        )

    client = _client(handler)

    appended = client.append_entry(
        "scratchpad_1",
        "finding",
    )

    listed = client.list_entries("scratchpad_1")

    cleared = client.clear_entries("scratchpad_1")

    assert isinstance(
        appended,
        validator.ScratchpadEntryRead,
    )

    assert isinstance(
        listed,
        validator.ScratchpadEntryList,
    )

    assert cleared.scope == "entries"

    assert calls == [
        (
            "POST",
            "/v1/scratchpads/scratchpad_1/entries",
        ),
        (
            "GET",
            "/v1/scratchpads/scratchpad_1/entries",
        ),
        (
            "DELETE",
            "/v1/scratchpads/scratchpad_1/entries",
        ),
    ]


def test_clear_scratchpad_contract() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.method == "POST"

        assert request.url.path == "/v1/scratchpads/scratchpad_1/clear"

        return httpx.Response(
            200,
            json={
                "id": "scratchpad_1",
                "object": "scratchpad.state.cleared",
                "scope": "all",
                "cleared": True,
            },
        )

    client = _client(handler)

    result = client.clear_scratchpad("scratchpad_1")

    assert isinstance(
        result,
        validator.ScratchpadStateCleared,
    )

    assert result.scope == "all"


def test_http_error_is_not_swallowed() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "detail": "Scratchpad not found",
            },
        )

    client = _client(handler)

    with pytest.raises(
        httpx.HTTPStatusError,
    ) as exc_info:
        client.retrieve_scratchpad("scratchpad_missing")

    assert exc_info.value.response.status_code == 404
