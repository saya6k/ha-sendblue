"""Thin async client for the Sendblue REST API."""

from typing import Any

import aiohttp

BASE_URL = "https://api.sendblue.com"
_TIMEOUT = aiohttp.ClientTimeout(total=30)
_RATE_LIMIT_CODES = {429, 4001, 5003, 5509}
_FREE_PLAN_LIMIT_CODES = {4007, 4008, 4009}


class SendblueError(Exception):
    """Base error for Sendblue API failures."""


class SendblueAuthError(SendblueError):
    """API key or secret was rejected."""


class SendblueContactNotVerified(SendblueError):
    """Recipient has not texted the shared line yet."""


class SendblueRateLimited(SendblueError):
    """Sendblue throttled the request."""


class SendblueFreePlanLimit(SendblueError):
    """Free plan limit before the recipient's first reply."""


class SendblueClient:
    """Thin async wrapper around the Sendblue REST API."""

    def __init__(
        self, session: aiohttp.ClientSession, key_id: str, secret: str
    ) -> None:
        self._session = session
        self._headers = {"sb-api-key-id": key_id, "sb-api-secret-key": secret}

    async def get_lines(self) -> list[str]:
        data = await self._request("GET", "/api/lines")
        return list(data.get("numbers", []))

    async def send_message(
        self,
        number: str,
        from_number: str,
        content: str | None = None,
        media_url: str | None = None,
        send_style: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"number": number, "from_number": from_number}
        body |= {
            k: v
            for k, v in (
                ("content", content),
                ("media_url", media_url),
                ("send_style", send_style),
            )
            if v
        }
        return await self._request("POST", "/api/send-message", body)

    async def list_webhook_urls(self) -> list[str]:
        data = await self._request("GET", "/api/account/webhooks")
        hooks = data.get("webhooks", {}).get("receive", [])
        return [h["url"] if isinstance(h, dict) else h for h in hooks]

    async def add_webhook(self, url: str, secret: str) -> None:
        await self._request(
            "POST",
            "/api/account/webhooks",
            {"webhooks": [{"url": url, "secret": secret}], "type": "receive"},
        )

    async def delete_webhook(self, url: str) -> None:
        await self._request(
            "DELETE", "/api/account/webhooks", {"webhooks": [url], "type": "receive"}
        )

    async def get_shared_contacts(self) -> dict[str, bool]:
        """Return verification state per number on the free shared line.

        Undocumented endpoint used by Sendblue's own CLI.
        """
        data = await self._request("GET", "/accounts/shared-contacts")
        return {c["number"]: bool(c.get("verified")) for c in data.get("contacts", [])}

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with self._session.request(
                method,
                BASE_URL + path,
                json=body,
                headers=self._headers,
                timeout=_TIMEOUT,
            ) as resp:
                status = resp.status
                try:
                    data = await resp.json(content_type=None)
                except ValueError:
                    data = {}
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SendblueError(f"Cannot reach Sendblue: {type(err).__name__}") from err

        if not isinstance(data, dict):
            data = {}
        if status in (401, 403):
            raise SendblueAuthError("Sendblue rejected the API credentials")
        if status >= 400 or data.get("status") == "ERROR":
            _raise_for_error(status, data)
        return data


def _raise_for_error(status: int, data: dict[str, Any]) -> None:
    message = data.get("error_message") or f"Sendblue returned HTTP {status}"
    code = data.get("error_code")
    if data.get("error_reason") == "ContactHasNotBeenVerified":
        raise SendblueContactNotVerified(message)
    if status == 429 or code in _RATE_LIMIT_CODES:
        raise SendblueRateLimited(message)
    if code in _FREE_PLAN_LIMIT_CODES:
        raise SendblueFreePlanLimit(message)
    raise SendblueError(message)
