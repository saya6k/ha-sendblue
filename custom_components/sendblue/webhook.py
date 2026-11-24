"""Incoming message webhook: registration with HA and Sendblue."""

import logging

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SendblueClient, SendblueError
from .const import (
    CONF_API_KEY_ID,
    CONF_API_SECRET_KEY,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def webhook_url(base_url: str, webhook_id: str) -> str:
    return f"{base_url}/api/webhook/{webhook_id}"


def client_for(hass: HomeAssistant, entry: ConfigEntry) -> SendblueClient:
    return SendblueClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY_ID],
        entry.data[CONF_API_SECRET_KEY],
    )


async def async_setup_webhook(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Receive on HA, then make sure Sendblue posts to us."""
    webhook.async_register(
        hass,
        DOMAIN,
        "Sendblue",
        entry.data[CONF_WEBHOOK_ID],
        async_handle_webhook,
        local_only=False,
        allowed_methods=["POST"],
    )

    url = webhook_url(entry.data[CONF_WEBHOOK_BASE_URL], entry.data[CONF_WEBHOOK_ID])
    issue_id = f"webhook_registration_failed_{entry.entry_id}"
    client = entry.runtime_data.client
    try:
        if url not in await client.list_webhook_urls():
            await client.add_webhook(url, entry.data[CONF_WEBHOOK_SECRET])
    except SendblueError as err:
        # Sending still works without it, so don't fail setup.
        _LOGGER.warning("Cannot register Sendblue webhook: %s", err)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="webhook_registration_failed",
        )
        return
    ir.async_delete_issue(hass, DOMAIN, issue_id)


def async_unload_webhook(hass: HomeAssistant, entry: ConfigEntry) -> None:
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])


async def async_delete_remote_webhook(
    hass: HomeAssistant, entry: ConfigEntry, base_url: str
) -> None:
    """Remove only our URL from Sendblue; other webhooks stay untouched."""
    url = webhook_url(base_url, entry.data[CONF_WEBHOOK_ID])
    try:
        await client_for(hass, entry).delete_webhook(url)
    except SendblueError as err:
        _LOGGER.warning("Cannot remove Sendblue webhook: %s", err)


async def async_handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response | None:
    return None
