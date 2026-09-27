"""Client for Project David MCP registration and assistant tool management."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any, Optional, overload

import httpx
from projectdavid_common import UtilsInterface, ValidationInterface
from projectdavid_common.schemas.mcp_schemas import McpServerAuth
from pydantic import BaseModel, ConfigDict

from projectdavid.clients.base_client import BaseAPIClient

validator = ValidationInterface()
logging_utility = UtilsInterface.LoggingUtility()


_MAX_DISCOVERY_PAGES = 100


class McpDiscoveredTool(BaseModel):
    """One tool advertised by a registered MCP server."""

    model_config = ConfigDict(frozen=True)

    server_id: str
    remote_name: str
    canonical_id: str
    provider_name: str
    definition: dict[str, Any]

    @property
    def name(self) -> str:
        """Human-facing MCP tool name."""
        return self.remote_name

    @property
    def description(self) -> str | None:
        """Function description advertised by the MCP server, when present."""
        function = self.definition.get("function")

        if not isinstance(function, dict):
            return None

        description = function.get("description")

        return description if isinstance(description, str) else None


class McpToolDiscoveryPage(BaseModel):
    """Typed representation of one Core MCP discovery page."""

    model_config = ConfigDict(frozen=True)

    tools: list[McpDiscoveredTool]
    next_cursor: str | None = None


class McpToolCollection(Sequence[McpDiscoveredTool]):
    """Read-only ergonomic view over discovered MCP tools."""

    def __init__(
        self,
        tools: Sequence[McpDiscoveredTool] = (),
    ) -> None:
        self._tools = tuple(tools)

    def __len__(self) -> int:
        return len(self._tools)

    @overload
    def __getitem__(self, index: int) -> McpDiscoveredTool: ...

    @overload
    def __getitem__(
        self,
        index: slice,
    ) -> tuple[McpDiscoveredTool, ...]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> McpDiscoveredTool | tuple[McpDiscoveredTool, ...]:
        return self._tools[index]

    def get(
        self,
        name: str,
    ) -> McpDiscoveredTool | None:
        """Return one discovered tool by remote name."""
        for tool in self._tools:
            if tool.remote_name == name:
                return tool

        return None

    def select(
        self,
        *names: str,
    ) -> "McpToolCollection":
        """Select named tools while preserving original discovery order."""
        available = {tool.remote_name for tool in self._tools}

        missing: list[str] = []
        seen_missing: set[str] = set()

        for name in names:
            if name not in available and name not in seen_missing:
                missing.append(name)
                seen_missing.add(name)

        if missing:
            raise ValueError("Unknown MCP tools: " + ", ".join(missing))

        requested = set(names)

        return McpToolCollection(
            [tool for tool in self._tools if tool.remote_name in requested]
        )

    def names(self) -> list[str]:
        return [tool.remote_name for tool in self._tools]

    def definitions(self) -> list[dict[str, Any]]:
        return [deepcopy(tool.definition) for tool in self._tools]

    def canonical_ids(self) -> list[str]:
        return [tool.canonical_id for tool in self._tools]


class McpClient(BaseAPIClient):
    """Manage MCP servers and their assistant tool attachments through Core."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(base_url=base_url, api_key=api_key)
        logging_utility.info(
            "McpClient initialized with base_url: %s",
            self.base_url,
        )

    @staticmethod
    def _registration_create_payload(
        request: validator.McpServerRegistrationCreate,
    ) -> dict[str, Any]:
        """
        Serialize an MCP registration request at the outbound HTTP boundary.

        Pydantic SecretStr values remain protected everywhere else. The raw
        bearer token is unwrapped only here because Core must receive it once
        in order to create the encrypted registration credential.
        """
        payload = request.model_dump(
            mode="json",
            exclude={"auth"},
        )

        auth_payload = request.auth.model_dump(
            mode="json",
            exclude={"token"},
            exclude_none=True,
        )

        if request.auth.type != "none":
            if request.auth.token is not None:
                auth_payload["token"] = request.auth.token.get_secret_value()

            payload["auth"] = auth_payload

        return payload

    def create_server(
        self,
        *,
        name: str,
        url: str,
        auth: McpServerAuth | None = None,
        bearer_token: str | None = None,
        transport: str = "streamable_http",
        timeout_seconds: float = 30.0,
    ) -> validator.McpServerRegistrationRead:
        """
        Register a user-owned remote MCP server.

        Authentication is bound to the registration. Discovery, attachment,
        and execution therefore do not require the credential again.
        """
        if auth is not None and bearer_token is not None:
            raise ValueError("Provide either auth or bearer_token, not both.")

        if bearer_token is not None:
            auth = McpServerAuth(
                type="bearer",
                token=bearer_token,
            )

        if auth is None:
            auth = McpServerAuth()

        try:
            request = validator.McpServerRegistrationCreate(
                name=name,
                url=url,
                auth=auth,
                transport=transport,
                timeout_seconds=timeout_seconds,
            )

            payload = self._registration_create_payload(request)

            response = self.client.post(
                "/v1/mcp/servers",
                json=payload,
            )
            response.raise_for_status()

            return validator.McpServerRegistrationRead.model_validate(response.json())

        except httpx.HTTPStatusError as exc:
            # Do not log response bodies on the credential-bearing
            # registration path. An upstream implementation could reflect
            # request material in an error response.
            logging_utility.error(
                "HTTP %d while creating MCP server",
                exc.response.status_code,
            )
            raise

        except Exception:
            logging_utility.exception("Unexpected error creating MCP server")
            raise

    def list_servers(self) -> list[validator.McpServerRegistrationRead]:
        """List the authenticated user's MCP server registrations."""
        try:
            response = self.client.get("/v1/mcp/servers")
            response.raise_for_status()
            return [
                validator.McpServerRegistrationRead.model_validate(registration)
                for registration in response.json()
            ]
        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while listing MCP servers: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise
        except Exception:
            logging_utility.exception("Unexpected error listing MCP servers")
            raise

    def retrieve_server(
        self,
        server_id: str,
    ) -> validator.McpServerRegistrationRead:
        """Retrieve one MCP server registration."""
        try:
            response = self.client.get(f"/v1/mcp/servers/{server_id}")
            response.raise_for_status()
            return validator.McpServerRegistrationRead.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while retrieving MCP server %s: %s",
                exc.response.status_code,
                server_id,
                exc.response.text,
            )
            raise
        except Exception:
            logging_utility.exception(
                "Unexpected error retrieving MCP server %s",
                server_id,
            )
            raise

    def update_server(
        self,
        server_id: str,
        *,
        name: str | None = None,
        timeout_seconds: float | None = None,
        enabled: bool | None = None,
    ) -> validator.McpServerRegistrationRead:
        """Update the mutable fields of an MCP server registration."""
        try:
            payload = validator.McpServerRegistrationUpdate(
                name=name,
                timeout_seconds=timeout_seconds,
                enabled=enabled,
            ).model_dump(exclude_none=True, exclude_unset=True)
            response = self.client.patch(
                f"/v1/mcp/servers/{server_id}",
                json=payload,
            )
            response.raise_for_status()
            return validator.McpServerRegistrationRead.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while updating MCP server %s: %s",
                exc.response.status_code,
                server_id,
                exc.response.text,
            )
            raise
        except Exception:
            logging_utility.exception(
                "Unexpected error updating MCP server %s",
                server_id,
            )
            raise

    def delete_server(self, server_id: str) -> None:
        """Delete an MCP server registration."""
        try:
            response = self.client.delete(f"/v1/mcp/servers/{server_id}")
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while deleting MCP server %s: %s",
                exc.response.status_code,
                server_id,
                exc.response.text,
            )
            raise
        except Exception:
            logging_utility.exception(
                "Unexpected error deleting MCP server %s",
                server_id,
            )
            raise

    @staticmethod
    def _resolve_server_id(
        server: str | validator.McpServerRegistrationRead,
    ) -> str:
        if isinstance(server, str):
            server_id = server.strip()

            if not server_id:
                raise ValueError("MCP server id cannot be empty.")

            return server_id

        if isinstance(
            server,
            validator.McpServerRegistrationRead,
        ):
            return server.id

        raise TypeError(
            "server must be an MCP server id or " "McpServerRegistrationRead"
        )

    def discover_tools_page(
        self,
        server: str | validator.McpServerRegistrationRead,
        *,
        cursor: str | None = None,
    ) -> McpToolDiscoveryPage:
        """Discover exactly one page of tools from a registered MCP server."""
        server_id = self._resolve_server_id(server)

        try:
            path = f"/v1/mcp/servers/{server_id}/tools"

            if cursor is None:
                response = self.client.get(path)
            else:
                response = self.client.get(
                    path,
                    params={"cursor": cursor},
                )

            response.raise_for_status()

            return McpToolDiscoveryPage.model_validate(response.json())

        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while discovering MCP tools for server %s: %s",
                exc.response.status_code,
                server_id,
                exc.response.text,
            )
            raise
        except Exception:
            logging_utility.exception(
                "Unexpected error discovering MCP tools for server %s",
                server_id,
            )
            raise

    def discover_tools(
        self,
        server: str | validator.McpServerRegistrationRead,
    ) -> McpToolCollection:
        """Discover all tools, transparently following MCP pagination."""
        tools: list[McpDiscoveredTool] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()

        for _ in range(_MAX_DISCOVERY_PAGES):
            page = self.discover_tools_page(
                server,
                cursor=cursor,
            )

            tools.extend(page.tools)

            next_cursor = page.next_cursor

            if next_cursor is None:
                return McpToolCollection(tools)

            if next_cursor in seen_cursors:
                raise RuntimeError(
                    "MCP discovery returned a repeated pagination cursor."
                )

            seen_cursors.add(next_cursor)
            cursor = next_cursor

        raise RuntimeError(
            "MCP discovery exceeded the maximum pagination limit "
            f"({_MAX_DISCOVERY_PAGES} pages)."
        )

    def list_assistant_tools(
        self,
        assistant_id: str,
    ) -> list[validator.AssistantMcpToolRead]:
        """List MCP tools attached to an assistant."""
        try:
            response = self.client.get(f"/v1/assistants/{assistant_id}/mcp-tools")
            response.raise_for_status()
            return [
                validator.AssistantMcpToolRead.model_validate(tool)
                for tool in response.json()
            ]
        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while listing MCP tools for assistant %s: %s",
                exc.response.status_code,
                assistant_id,
                exc.response.text,
            )
            raise
        except Exception:
            logging_utility.exception(
                "Unexpected error listing MCP tools for assistant %s",
                assistant_id,
            )
            raise

    def attach_tools(
        self,
        assistant_id: str,
        *,
        tools: Sequence[McpDiscoveredTool],
    ) -> list[validator.AssistantMcpToolRead]:
        """Attach discovered MCP tools without repeating server provenance."""
        selected = list(tools)

        if not selected:
            raise ValueError("At least one discovered MCP tool is required.")

        if not all(isinstance(tool, McpDiscoveredTool) for tool in selected):
            raise TypeError("tools must contain McpDiscoveredTool instances.")

        server_ids = {tool.server_id for tool in selected}

        if len(server_ids) != 1:
            raise ValueError("All attached MCP tools must belong to the same server.")

        server_id = next(iter(server_ids))

        remote_names: list[str] = []
        seen_names: set[str] = set()

        for tool in selected:
            if tool.remote_name in seen_names:
                continue

            remote_names.append(tool.remote_name)
            seen_names.add(tool.remote_name)

        return self.attach_assistant_tools(
            assistant_id,
            server_id=server_id,
            tools=remote_names,
        )

    def attach_assistant_tools(
        self,
        assistant_id: str,
        *,
        server_id: str,
        tools: list[str],
    ) -> list[validator.AssistantMcpToolRead]:
        """Attach selected registered MCP tools to an assistant."""
        try:
            payload = validator.AssistantMcpToolsAttach(
                server_id=server_id,
                tools=tools,
            ).model_dump()
            response = self.client.post(
                f"/v1/assistants/{assistant_id}/mcp-tools",
                json=payload,
            )
            response.raise_for_status()
            return [
                validator.AssistantMcpToolRead.model_validate(tool)
                for tool in response.json()
            ]
        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while attaching MCP tools to assistant %s: %s",
                exc.response.status_code,
                assistant_id,
                exc.response.text,
            )
            raise
        except Exception:
            logging_utility.exception(
                "Unexpected error attaching MCP tools to assistant %s",
                assistant_id,
            )
            raise

    def detach_assistant_tools(
        self,
        assistant_id: str,
        *,
        server_id: str,
        tools: list[str],
    ) -> None:
        """Detach selected MCP tools from an assistant."""
        try:
            payload = validator.AssistantMcpToolsDetach(
                server_id=server_id,
                tools=tools,
            ).model_dump()
            response = self.client.request(
                "DELETE",
                f"/v1/assistants/{assistant_id}/mcp-tools",
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while detaching MCP tools from assistant %s: %s",
                exc.response.status_code,
                assistant_id,
                exc.response.text,
            )
            raise
        except Exception:
            logging_utility.exception(
                "Unexpected error detaching MCP tools from assistant %s",
                assistant_id,
            )
            raise
