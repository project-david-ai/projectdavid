"""Typed client for tenant-owned inference provider credentials (BYOK)."""

from __future__ import annotations

from projectdavid_common import ValidationInterface

from projectdavid.clients.base_client import BaseAPIClient

validator = ValidationInterface()


class ProviderKeysClient(BaseAPIClient):
    """Manage provider keys without exposing stored secret material."""

    def create(
        self,
        *,
        provider: str,
        api_key: str,
        name: str | None = None,
    ) -> validator.ProviderKeyRead:
        """Register a provider key; duplicate active registrations are idempotent."""
        registration = validator.ProviderKeyCreate(
            provider=provider,
            api_key=api_key,
            name=name,
        )
        # SecretStr is excluded from ordinary Pydantic serialization. Unwrap
        # only for the outbound HTTPS request; never log its body.
        payload = registration.model_dump(
            mode="json", exclude={"api_key"}, exclude_none=True
        )
        payload["api_key"] = registration.api_key.get_secret_value()

        response = self.client.post("/v1/provider-keys", json=payload)
        response.raise_for_status()
        return validator.ProviderKeyRead.model_validate(response.json())

    def list(self) -> list[validator.ProviderKeyRead]:
        """List the authenticated user's provider keys, including revoked ones."""
        response = self.client.get("/v1/provider-keys")
        response.raise_for_status()
        return [
            validator.ProviderKeyRead.model_validate(item) for item in response.json()
        ]

    def retrieve(self, provider_key_id: str) -> validator.ProviderKeyRead:
        """Retrieve non-secret metadata for one provider key."""
        response = self.client.get(f"/v1/provider-keys/{provider_key_id}")
        response.raise_for_status()
        return validator.ProviderKeyRead.model_validate(response.json())

    def update(self, provider_key_id: str, *, name: str) -> validator.ProviderKeyRead:
        """Rename a provider key; replacing credential material is unsupported."""
        update = validator.ProviderKeyUpdate(name=name)
        response = self.client.patch(
            f"/v1/provider-keys/{provider_key_id}",
            json=update.model_dump(mode="json"),
        )
        response.raise_for_status()
        return validator.ProviderKeyRead.model_validate(response.json())

    def revoke(self, provider_key_id: str) -> None:
        """Revoke a provider key (HTTP 204)."""
        response = self.client.delete(f"/v1/provider-keys/{provider_key_id}")
        response.raise_for_status()


__all__ = ["ProviderKeysClient"]
