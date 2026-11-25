"""Incoming message webhook: registration with HA and Sendblue."""

import hmac
import logging
from functools import partial

from aiohttp import web
from homeassistant.components import assist_pipeline, conversation, webhook
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SendblueClient, SendblueError
from .const import (
    CONF_ADDRESS,
    CONF_API_KEY_ID,
    CONF_API_SECRET_KEY,
    CONF_ASSIST_ENABLED,
    CONF_CONVERSATION_AGENT_ID,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    SUBENTRY_RECIPIENT,
)

_LOGGER = logging.getLogger(__name__)
ASSIST_ERROR_REPLY = "Sorry, Home Assistant could not handle that message."


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
        # Bound to the entry: it is not "loaded" yet while setup below runs,
        # and messages already arrive then.
        partial(async_handle_webhook, entry),
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
    entry: ConfigEntry, hass: HomeAssistant, webhook_id: str, request: web.Request
) -> web.Response:
    given = request.headers.get("sb-signing-secret", "")
    if not hmac.compare_digest(given.encode(), entry.data[CONF_WEBHOOK_SECRET].encode()):
        return web.Response(status=401)
    try:
        payload = await request.json()
    except ValueError:
        return web.Response(status=400)
    if not isinstance(payload, dict):
        return web.Response(status=400)

    if payload.get("is_outbound") or payload.get("group_id"):
        return web.Response(status=200)
    handle = payload.get("message_handle")
    seen = entry.runtime_data.seen_handles
    if handle:
        if handle in seen:
            return web.Response(status=200)
        seen.append(handle)

    sender = str(payload.get("from_number") or "")
    content = str(payload.get("content") or "")
    recipient = _find_recipient(entry, sender)
    hass.bus.async_fire(
        EVENT_MESSAGE_RECEIVED,
        {
            "entry_id": entry.entry_id,
            "from_number": sender,
            "content": content,
            "media_url": payload.get("media_url") or "",
            "service": payload.get("service"),
            "message_handle": handle,
            "recipient_subentry_id": recipient.subentry_id if recipient else None,
            "recipient_name": recipient.title if recipient else None,
        },
    )
    # Only allowlisted recipients may reach Assist, and only over iMessage:
    # SMS sender numbers can be spoofed. Reply after acking so a slow agent
    # never trips Sendblue's 45 s timeout and retries.
    if (
        recipient
        and recipient.data[CONF_ASSIST_ENABLED]
        and payload.get("service") == "iMessage"
        and content.strip()
    ):
        # Answer from the line that was texted, so the reply stays in its thread.
        line = str(payload.get("to_number") or "")
        entry.async_create_background_task(
            hass, _async_assist_reply(hass, entry, sender, line, content), "sendblue_assist"
        )
    return web.Response(status=200)


async def _async_assist_reply(
    hass: HomeAssistant, entry: ConfigEntry, sender: str, line: str, text: str
) -> None:
    agent_id, language = _resolve_agent(hass, entry)
    try:
        result = await conversation.async_converse(
            hass,
            text=text,
            conversation_id=f"sendblue_{entry.entry_id}_{sender}",
            context=Context(),
            language=language,
            agent_id=agent_id,
        )
        speech = result.response.speech.get("plain", {}).get("speech", "")
    except Exception:
        _LOGGER.exception("Assist failed to handle a Sendblue message")
        speech = ASSIST_ERROR_REPLY
    if not speech:
        return

    runtime = entry.runtime_data
    try:
        await runtime.client.send_message(
            sender, line or runtime.coordinator.data.from_number, content=speech
        )
    except SendblueError as err:
        _LOGGER.warning("Cannot send Assist reply: %s", err)


def _resolve_agent(hass: HomeAssistant, entry: ConfigEntry) -> tuple[str, str]:
    """Use the configured agent, else the preferred Assist pipeline's agent."""
    if agent_id := entry.options.get(CONF_CONVERSATION_AGENT_ID):
        return agent_id, hass.config.language
    # async_converse alone would fall back to the built-in agent, not the
    # pipeline the user picked as preferred.
    if "assist_pipeline" in hass.config.components:
        pipeline = assist_pipeline.async_get_pipeline(hass)
        language = pipeline.conversation_language
        if language == "*":
            language = hass.config.language
        return pipeline.conversation_engine, language
    return conversation.HOME_ASSISTANT_AGENT, hass.config.language


def _find_recipient(entry: ConfigEntry, sender: str) -> ConfigSubentry | None:
    sender = sender.lower()
    return next(
        (
            sub
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_RECIPIENT and sub.data[CONF_ADDRESS] == sender
        ),
        None,
    )
