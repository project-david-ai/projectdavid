from __future__ import annotations

from typing import Any, Dict, Optional, Type, TypeVar

import httpx
from projectdavid_common import UtilsInterface, ValidationInterface
from pydantic import BaseModel, ValidationError

from projectdavid.clients.base_client import BaseAPIClient

validator = ValidationInterface()
logging_utility = UtilsInterface.LoggingUtility()

ModelT = TypeVar(
    "ModelT",
    bound=BaseModel,
)


class ScratchpadsClient(BaseAPIClient):
    """
    First-class Scratchpad resource client.

    This is distinct from ToolsClient.scratchpad_*.

    ToolsClient retains the model-facing thread compatibility API.
    ScratchpadsClient addresses canonical Scratchpad resources by ID.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        super().__init__(
            base_url=base_url,
            api_key=api_key,
        )

        logging_utility.info(
            "ScratchpadsClient initialized with base_url: %s",
            self.base_url,
        )

    def _request_model(
        self,
        method: str,
        path: str,
        response_model: Type[ModelT],
        *,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ModelT:
        try:
            response = self.client.request(
                method,
                path,
                json=payload,
            )

            response.raise_for_status()

            return response_model.model_validate(response.json())

        except ValidationError as exc:
            logging_utility.error(
                "Scratchpad response validation failed for %s %s: %s",
                method,
                path,
                exc,
            )

            raise ValueError(f"Scratchpad response validation failed: {exc}") from exc

        except httpx.HTTPStatusError as exc:
            logging_utility.error(
                "Scratchpad request failed: %s %s | status=%s | body=%s",
                method,
                path,
                exc.response.status_code,
                exc.response.text,
            )

            raise

        except Exception as exc:
            logging_utility.error(
                "Unexpected Scratchpad client error for %s %s: %s",
                method,
                path,
                exc,
            )

            raise

    # ------------------------------------------------------------------
    # Resource plane
    # ------------------------------------------------------------------

    def create_scratchpad(
        self,
        thread_id: str,
    ) -> validator.ScratchpadRead:
        payload = validator.ScratchpadCreate(
            thread_id=thread_id,
        ).model_dump()

        return self._request_model(
            "POST",
            "/v1/scratchpads",
            validator.ScratchpadRead,
            payload=payload,
        )

    def retrieve_scratchpad(
        self,
        scratchpad_id: str,
    ) -> validator.ScratchpadRead:
        return self._request_model(
            "GET",
            f"/v1/scratchpads/{scratchpad_id}",
            validator.ScratchpadRead,
        )

    def retrieve_scratchpad_by_thread(
        self,
        thread_id: str,
    ) -> validator.ScratchpadRead:
        return self._request_model(
            "GET",
            f"/v1/threads/{thread_id}/scratchpad",
            validator.ScratchpadRead,
        )

    def list_scratchpads(
        self,
    ) -> validator.ScratchpadList:
        return self._request_model(
            "GET",
            "/v1/scratchpads",
            validator.ScratchpadList,
        )

    def update_scratchpad(
        self,
        scratchpad_id: str,
        *,
        meta_data: Dict[str, Any],
    ) -> validator.ScratchpadRead:
        payload = validator.ScratchpadUpdate(
            meta_data=meta_data,
        ).model_dump(exclude_none=True)

        return self._request_model(
            "PATCH",
            f"/v1/scratchpads/{scratchpad_id}",
            validator.ScratchpadRead,
            payload=payload,
        )

    def delete_scratchpad(
        self,
        scratchpad_id: str,
    ) -> validator.ScratchpadDeleted:
        return self._request_model(
            "DELETE",
            f"/v1/scratchpads/{scratchpad_id}",
            validator.ScratchpadDeleted,
        )

    # ------------------------------------------------------------------
    # Content plane
    # ------------------------------------------------------------------

    def get_content(
        self,
        scratchpad_id: str,
    ) -> validator.ScratchpadContentRead:
        return self._request_model(
            "GET",
            f"/v1/scratchpads/{scratchpad_id}/content",
            validator.ScratchpadContentRead,
        )

    def set_content(
        self,
        scratchpad_id: str,
        content: str,
    ) -> validator.ScratchpadContentRead:
        payload = validator.ScratchpadContentUpdate(
            content=content,
        ).model_dump()

        return self._request_model(
            "PUT",
            f"/v1/scratchpads/{scratchpad_id}/content",
            validator.ScratchpadContentRead,
            payload=payload,
        )

    def clear_content(
        self,
        scratchpad_id: str,
    ) -> validator.ScratchpadStateCleared:
        return self._request_model(
            "DELETE",
            f"/v1/scratchpads/{scratchpad_id}/content",
            validator.ScratchpadStateCleared,
        )

    # ------------------------------------------------------------------
    # Entry ledger
    # ------------------------------------------------------------------

    def append_entry(
        self,
        scratchpad_id: str,
        content: str,
    ) -> validator.ScratchpadEntryRead:
        payload = validator.ScratchpadEntryCreate(
            content=content,
        ).model_dump()

        return self._request_model(
            "POST",
            f"/v1/scratchpads/{scratchpad_id}/entries",
            validator.ScratchpadEntryRead,
            payload=payload,
        )

    def list_entries(
        self,
        scratchpad_id: str,
    ) -> validator.ScratchpadEntryList:
        return self._request_model(
            "GET",
            f"/v1/scratchpads/{scratchpad_id}/entries",
            validator.ScratchpadEntryList,
        )

    def clear_entries(
        self,
        scratchpad_id: str,
    ) -> validator.ScratchpadStateCleared:
        return self._request_model(
            "DELETE",
            f"/v1/scratchpads/{scratchpad_id}/entries",
            validator.ScratchpadStateCleared,
        )

    # ------------------------------------------------------------------
    # Mutable-state lifecycle
    # ------------------------------------------------------------------

    def clear_scratchpad(
        self,
        scratchpad_id: str,
    ) -> validator.ScratchpadStateCleared:
        return self._request_model(
            "POST",
            f"/v1/scratchpads/{scratchpad_id}/clear",
            validator.ScratchpadStateCleared,
        )


__all__ = ["ScratchpadsClient"]
