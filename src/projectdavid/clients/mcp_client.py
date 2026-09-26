"""Client for Project David MCP registration and assistant tool management."""

from __future__ import annotations

from typing import Any, Optional

import httpx
from projectdavid_common import UtilsInterface, ValidationInterface

from projectdavid.clients.base_client import BaseAPIClient

validator = ValidationInterface()
logging_utility = UtilsInterface.LoggingUtility()


class McpClient(BaseAPIClient):
    """Manage MCP servers and their assistant tool attachments through Core."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__(base_url=base_url, api_key=api_key)
        logging_utility.info(
            "McpClient initialized with base_url: %s",
            self.base_url,
        )

    def create_server(
        self,
        *,
        name: str,
        url: str,
        transport: str = "streamable_http",
        timeout_seconds: float = 30.0,
    ) -> validator.McpServerRegistrationRead:
        """Register a user-owned remote MCP server."""
        try:
            payload = validator.McpServerRegistrationCreate(
                name=name,
                url=url,
                transport=transport,
                timeout_seconds=timeout_seconds,
            ).model_dump(mode="json")
            response = self.client.post("/v1/mcp/servers", json=payload)
            response.raise_for_status()
            return validator.McpServerRegistrationRead.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "HTTP %d while creating MCP server: %s",
                exc.response.status_code,
                exc.response.text,
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

    def discover_tools(
        self,
        server_id: str,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Discover one page of tools exposed by a registered MCP server."""
        try:
            path = f"/v1/mcp/servers/{server_id}/tools"
            if cursor is None:
                response = self.client.get(path)
            else:
                response = self.client.get(path, params={"cursor": cursor})
            response.raise_for_status()
            return response.json()
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
