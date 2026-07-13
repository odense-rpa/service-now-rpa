"""ServiceNow Table API client with OAuth client-credentials auth."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from .settings import Settings

DEFAULT_INSTANCE = "https://odense.service-now.com"

# Refresh the token this many seconds before it actually expires.
TOKEN_EXPIRY_MARGIN = 60


class ServiceNowError(Exception):
    """Raised when the ServiceNow API returns an error response."""

    def __init__(self, status_code: int, message: str, detail: str | None = None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {message}" + (f" ({detail})" if detail else ""))


class ServiceNowClient:
    """Client for the ServiceNow Table API.

    Usage (production — credentials from your credential store):
        client = ServiceNowClient(client_id=cred.username, client_secret=cred.password, scope="RPA 1")
        record = client.get_record("service_offering", "52ad61f4...")
        for row in client.query("service_offering", query="active=true"):
            ...

    For local development/tests, ServiceNowClient.from_env() reads a .env file.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        scope: str = "",
        instance: str = DEFAULT_INSTANCE,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.instance = instance
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._http = httpx.Client(base_url=instance, timeout=timeout, transport=transport)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @classmethod
    def from_env(cls, env_file: str = ".env", **kwargs: Any) -> ServiceNowClient:
        """Build a client from environment variables / a .env file (dev and test use).

        In production, pass credentials to the constructor instead.
        """
        settings = Settings(_env_file=env_file)
        return cls(
            settings.client_id,
            settings.client_secret,
            scope=settings.client_scope,
            instance=settings.instance_url,
            **kwargs,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ServiceNowClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- auth -----------------------------------------------------------

    def _fetch_token(self) -> None:
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if self._scope:
            data["scope"] = self._scope
        response = self._http.post("/oauth_token.do", data=data)
        if response.status_code != 200:
            raise ServiceNowError(response.status_code, "token request failed", response.text[:500])
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.monotonic() + int(payload.get("expires_in", 1799)) - TOKEN_EXPIRY_MARGIN

    def _auth_headers(self) -> dict[str, str]:
        if self._token is None or time.monotonic() >= self._token_expires_at:
            self._fetch_token()
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    # --- reads ----------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._http.get(path, params=params, headers=self._auth_headers())
        if response.status_code == 401:
            # Token may have been revoked server-side; retry once with a fresh one.
            self._token = None
            response = self._http.get(path, params=params, headers=self._auth_headers())
        if response.status_code != 200:
            detail = None
            try:
                detail = response.json().get("error", {}).get("message")
            except Exception:
                detail = response.text[:500]
            raise ServiceNowError(response.status_code, f"GET {path} failed", detail)
        return response.json()

    def get_record(
        self,
        table: str,
        sys_id: str,
        *,
        fields: list[str] | None = None,
        display_value: bool | str = False,
    ) -> dict[str, Any]:
        """Fetch a single record by sys_id."""
        params: dict[str, Any] = {"sysparm_display_value": display_value}
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        return self._get(f"/api/now/table/{table}/{sys_id}", params)["result"]

    def query(
        self,
        table: str,
        *,
        query: str | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        display_value: bool | str = False,
    ) -> list[dict[str, Any]]:
        """Fetch a single page of records from a table.

        `query` is a ServiceNow encoded query, e.g. "active=true^nameLIKEpagt".
        """
        params: dict[str, Any] = {
            "sysparm_limit": limit,
            "sysparm_offset": offset,
            "sysparm_display_value": display_value,
            "sysparm_exclude_reference_link": "true",
        }
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        return self._get(f"/api/now/table/{table}", params)["result"]

    # --- writes ---------------------------------------------------------
    # NOTE: this talks to the live production instance. Prefer the scoped
    # RpaClient (snow.rpa) over calling these directly.

    def _send(self, method: str, path: str, body: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = self._auth_headers() | {"Content-Type": "application/json"}
        response = self._http.request(method, path, json=body, params=params, headers=headers)
        if response.status_code == 401:
            self._token = None
            headers = self._auth_headers() | {"Content-Type": "application/json"}
            response = self._http.request(method, path, json=body, params=params, headers=headers)
        if response.status_code not in (200, 201):
            try:
                detail = response.json().get("error", {}).get("message")
            except Exception:
                detail = response.text[:500]
            raise ServiceNowError(response.status_code, f"{method} {path} failed", detail)
        return response.json()

    def update_record(
        self, table: str, sys_id: str, payload: dict[str, Any], *, fields: list[str] | None = None
    ) -> dict[str, Any]:
        """PATCH fields on an existing record; returns the updated record."""
        params: dict[str, Any] = {"sysparm_exclude_reference_link": "true"}
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        return self._send("PATCH", f"/api/now/table/{table}/{sys_id}", payload, params)["result"]

    def create_record(
        self, table: str, payload: dict[str, Any], *, fields: list[str] | None = None
    ) -> dict[str, Any]:
        """POST a new record; returns the created record."""
        params: dict[str, Any] = {"sysparm_exclude_reference_link": "true"}
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        return self._send("POST", f"/api/now/table/{table}", payload, params)["result"]

    def query_all(
        self,
        table: str,
        *,
        query: str | None = None,
        fields: list[str] | None = None,
        page_size: int = 200,
        display_value: bool | str = False,
    ) -> Iterator[dict[str, Any]]:
        """Iterate over all records matching a query, paginating transparently."""
        offset = 0
        while True:
            page = self.query(
                table,
                query=query,
                fields=fields,
                limit=page_size,
                offset=offset,
                display_value=display_value,
            )
            yield from page
            if len(page) < page_size:
                return
            offset += page_size
