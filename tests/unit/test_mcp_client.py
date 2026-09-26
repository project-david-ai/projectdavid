import json
from unittest.mock import patch

import httpx
import pytest
from projectdavid_common import ValidationInterface

from projectdavid import Entity
from projectdavid.clients.mcp_client import (
    McpClient,
    McpDiscoveredTool,
    McpToolCollection,
)

validator = ValidationInterface()


def _server_payload(server_id: str = "mcp_server_1", **overrides):
    payload = {
        "id": server_id,
        "owner_id": "user_1",
        "name": "github",
        "url": "https://example.com/mcp",
        "transport": "streamable_http",
        "timeout_seconds": 30.0,
        "enabled": True,
        "created_at": "2026-09-26T12:00:00Z",
        "updated_at": "2026-09-26T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def _assistant_tool_payload(remote_name: str = "search.issues"):
    return {
        "id": "assistant_mcp_tool_1",
        "assistant_id": "assistant_1",
        "registration_id": "mcp_server_1",
        "remote_name": remote_name,
        "canonical_id": f"github.{remote_name}",
        "provider_name": "github",
        "enabled": True,
        "created_at": "2026-09-26T12:00:00Z",
    }


def _discovered_tool_payload(
    remote_name: str,
    *,
    server_id: str = "mcp_server_1",
    description: str | None = None,
):
    function = {
        "name": f"github__{remote_name.replace('.', '_')}",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    }

    if description is not None:
        function["description"] = description

    return {
        "server_id": server_id,
        "remote_name": remote_name,
        "canonical_id": f"{server_id}:{remote_name}",
        "provider_name": function["name"],
        "definition": {
            "type": "function",
            "function": function,
        },
    }


def _client(handler):
    client = McpClient(
        base_url="https://project-david.test",
        api_key="pd-key",
    )
    client.client.close()
    client.client = httpx.Client(
        base_url=client.base_url,
        headers={"X-API-Key": client.api_key},
        transport=httpx.MockTransport(handler),
    )
    return client


def test_create_server_validates_payload_and_response():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_server_payload())

    with _client(handler) as client:
        result = client.create_server(
            name="github",
            url="https://example.com/mcp",
        )

    assert type(result) is validator.McpServerRegistrationRead
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/mcp/servers"
    assert json.loads(requests[0].content) == {
        "name": "github",
        "url": "https://example.com/mcp",
        "transport": "streamable_http",
        "timeout_seconds": 30.0,
    }


def test_list_servers_preserves_server_order_and_validates_models():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                _server_payload("mcp_server_2", name="second"),
                _server_payload("mcp_server_1", name="first"),
            ],
        )

    with _client(handler) as client:
        result = client.list_servers()

    assert [server.id for server in result] == ["mcp_server_2", "mcp_server_1"]
    assert all(type(server) is validator.McpServerRegistrationRead for server in result)
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/mcp/servers"
    assert requests[0].url.query == b""


def test_retrieve_server_uses_registration_endpoint():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_server_payload())

    with _client(handler) as client:
        result = client.retrieve_server("mcp_server_1")

    assert type(result) is validator.McpServerRegistrationRead
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/mcp/servers/mcp_server_1"


def test_update_server_omits_unset_and_none_fields():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=_server_payload(name="renamed", enabled=False),
        )

    with _client(handler) as client:
        result = client.update_server(
            "mcp_server_1",
            name="renamed",
            enabled=False,
        )

    assert result.name == "renamed"
    assert result.enabled is False
    assert requests[0].method == "PATCH"
    assert requests[0].url.path == "/v1/mcp/servers/mcp_server_1"
    assert json.loads(requests[0].content) == {
        "name": "renamed",
        "enabled": False,
    }


def test_delete_server_returns_none_without_parsing_204_body():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(204)

    with _client(handler) as client:
        result = client.delete_server("mcp_server_1")

    assert result is None
    assert requests[0].method == "DELETE"
    assert requests[0].url.path == "/v1/mcp/servers/mcp_server_1"
    assert requests[0].content == b""


def test_discover_tools_page_returns_typed_page():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "tools": [
                    _discovered_tool_payload(
                        "search.issues",
                        description="Search repository issues",
                    )
                ],
                "next_cursor": "page_2",
            },
        )

    with _client(handler) as client:
        page = client.discover_tools_page("mcp_server_1")

    assert page.next_cursor == "page_2"
    assert len(page.tools) == 1
    assert type(page.tools[0]) is McpDiscoveredTool
    assert page.tools[0].name == "search.issues"
    assert page.tools[0].description == "Search repository issues"
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/mcp/servers/mcp_server_1/tools"
    assert requests[0].url.query == b""


def test_discover_tools_page_accepts_registration_model_and_cursor():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "tools": [],
                "next_cursor": None,
            },
        )

    server = validator.McpServerRegistrationRead.model_validate(_server_payload())

    with _client(handler) as client:
        page = client.discover_tools_page(
            server,
            cursor="page_2",
        )

    assert page.tools == []
    assert requests[0].url.path == "/v1/mcp/servers/mcp_server_1/tools"
    assert dict(requests[0].url.params) == {"cursor": "page_2"}


def test_discover_tools_auto_paginates_into_collection():
    requests = []

    def handler(request):
        requests.append(request)

        cursor = request.url.params.get("cursor")

        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "tools": [
                        _discovered_tool_payload(
                            "search.issues",
                            description="Search issues",
                        )
                    ],
                    "next_cursor": "page_2",
                },
            )

        assert cursor == "page_2"

        return httpx.Response(
            200,
            json={
                "tools": [
                    _discovered_tool_payload(
                        "get.issue",
                        description="Get one issue",
                    )
                ],
                "next_cursor": None,
            },
        )

    with _client(handler) as client:
        tools = client.discover_tools("mcp_server_1")

    assert type(tools) is McpToolCollection
    assert tools.names() == [
        "search.issues",
        "get.issue",
    ]
    assert len(requests) == 2


def test_discover_tools_rejects_repeated_cursor():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "tools": [],
                "next_cursor": "same_cursor",
            },
        )

    with _client(handler) as client:
        with pytest.raises(
            RuntimeError,
            match="repeated pagination cursor",
        ):
            client.discover_tools("mcp_server_1")


def test_tool_collection_helpers_and_selection_preserve_order():
    tools = McpToolCollection(
        [
            McpDiscoveredTool.model_validate(
                _discovered_tool_payload(
                    "search.issues",
                    description="Search issues",
                )
            ),
            McpDiscoveredTool.model_validate(
                _discovered_tool_payload(
                    "get.issue",
                    description="Get issue",
                )
            ),
            McpDiscoveredTool.model_validate(
                _discovered_tool_payload(
                    "create.issue",
                    description="Create issue",
                )
            ),
        ]
    )

    assert len(tools) == 3
    assert tools[0].name == "search.issues"
    assert tools.get("get.issue").description == "Get issue"
    assert tools.get("does.not.exist") is None

    selected = tools.select(
        "create.issue",
        "search.issues",
        "search.issues",
    )

    # Selection order follows authoritative discovery order.
    assert selected.names() == [
        "search.issues",
        "create.issue",
    ]

    assert selected.canonical_ids() == [
        "mcp_server_1:search.issues",
        "mcp_server_1:create.issue",
    ]

    definitions = selected.definitions()

    assert definitions[0]["function"]["description"] == "Search issues"

    # Returned definitions are copies, not references into the collection.
    definitions[0]["function"]["description"] = "changed"

    assert selected[0].description == "Search issues"


def test_tool_collection_select_rejects_unknown_names():
    tools = McpToolCollection(
        [McpDiscoveredTool.model_validate(_discovered_tool_payload("search.issues"))]
    )

    with pytest.raises(
        ValueError,
        match="Unknown MCP tools: missing.tool",
    ):
        tools.select(
            "search.issues",
            "missing.tool",
        )


def test_list_assistant_tools_validates_models():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[_assistant_tool_payload()])

    with _client(handler) as client:
        result = client.list_assistant_tools("assistant_1")

    assert len(result) == 1
    assert type(result[0]) is validator.AssistantMcpToolRead
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/assistants/assistant_1/mcp-tools"


def test_attach_assistant_tools_sends_validated_body_and_validates_response():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[_assistant_tool_payload()])

    with _client(handler) as client:
        result = client.attach_assistant_tools(
            "assistant_1",
            server_id="mcp_server_1",
            tools=["search.issues"],
        )

    assert type(result[0]) is validator.AssistantMcpToolRead
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/assistants/assistant_1/mcp-tools"
    assert json.loads(requests[0].content) == {
        "server_id": "mcp_server_1",
        "tools": ["search.issues"],
    }


def test_detach_assistant_tools_sends_json_delete_body_and_returns_none():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(204)

    with _client(handler) as client:
        result = client.detach_assistant_tools(
            "assistant_1",
            server_id="mcp_server_1",
            tools=["search.issues"],
        )

    assert result is None
    assert requests[0].method == "DELETE"
    assert requests[0].url.path == "/v1/assistants/assistant_1/mcp-tools"
    assert json.loads(requests[0].content) == {
        "server_id": "mcp_server_1",
        "tools": ["search.issues"],
    }


def test_attach_tools_infers_server_and_uses_remote_names():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                _assistant_tool_payload("search.issues"),
                _assistant_tool_payload("get.issue"),
            ],
        )

    tools = McpToolCollection(
        [
            McpDiscoveredTool.model_validate(_discovered_tool_payload("search.issues")),
            McpDiscoveredTool.model_validate(_discovered_tool_payload("get.issue")),
            McpDiscoveredTool.model_validate(_discovered_tool_payload("create.issue")),
        ]
    )

    selected = tools.select(
        "search.issues",
        "get.issue",
    )

    with _client(handler) as client:
        result = client.attach_tools(
            "assistant_1",
            tools=selected,
        )

    assert len(result) == 2
    assert all(type(tool) is validator.AssistantMcpToolRead for tool in result)

    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/assistants/assistant_1/mcp-tools"
    assert json.loads(requests[0].content) == {
        "server_id": "mcp_server_1",
        "tools": [
            "search.issues",
            "get.issue",
        ],
    }


def test_attach_tools_rejects_empty_collection():
    def handler(request):
        raise AssertionError("HTTP request should not occur")

    with _client(handler) as client:
        with pytest.raises(
            ValueError,
            match="At least one discovered MCP tool",
        ):
            client.attach_tools(
                "assistant_1",
                tools=McpToolCollection(),
            )


def test_attach_tools_rejects_mixed_server_collection():
    def handler(request):
        raise AssertionError("HTTP request should not occur")

    tools = McpToolCollection(
        [
            McpDiscoveredTool.model_validate(
                _discovered_tool_payload(
                    "search.issues",
                    server_id="mcp_server_1",
                )
            ),
            McpDiscoveredTool.model_validate(
                _discovered_tool_payload(
                    "get.issue",
                    server_id="mcp_server_2",
                )
            ),
        ]
    )

    with _client(handler) as client:
        with pytest.raises(
            ValueError,
            match="same server",
        ):
            client.attach_tools(
                "assistant_1",
                tools=tools,
            )


def test_entity_mcp_is_lazy_and_reuses_the_same_instance():
    sentinel = object()

    with patch("projectdavid.entity.McpClient", return_value=sentinel) as client_type:
        entity = Entity(
            base_url="https://project-david.test",
            api_key="pd-key",
        )

        client_type.assert_not_called()
        first = entity.mcp
        second = entity.mcp

    assert first is sentinel
    assert second is sentinel
    client_type.assert_called_once_with(
        base_url="https://project-david.test",
        api_key="pd-key",
    )


def test_http_errors_are_propagated():
    def handler(request):
        return httpx.Response(500, json={"detail": "server error"})

    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            client.list_servers()

    assert exc_info.value.response.status_code == 500
