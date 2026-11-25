"""Tests for the incoming message webhook and Assist replies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.conversation import ConversationResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from custom_components.sendblue.api import SendblueClient
from tests.vendor.ha_common import async_capture_events

from .conftest import LINE, MOM, mock_webhooks

URL = "/api/webhook/hook-id"
HEADERS = {"sb-signing-secret": "hook-secret"}
EVENT = "sendblue_message_received"


def _payload(**overrides) -> dict:
    return {
        "content": "Turn off the lights",
        "is_outbound": False,
        "status": "RECEIVED",
        "message_handle": "BF63384D-A5C4-491A-BDDD-161978DCFD5C",
        "from_number": MOM,
        "to_number": LINE,
        "media_url": "",
        "group_id": "",
        "service": "iMessage",
        **overrides,
    }


@pytest.fixture
async def client(hass: HomeAssistant, mock_entry, mock_api, hass_client_no_auth):
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    return await hass_client_no_auth()


async def test_message_from_recipient_fires_event(hass: HomeAssistant, client, mock_entry) -> None:
    events = async_capture_events(hass, EVENT)

    resp = await client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    assert resp.status == 200
    subentry_id = next(iter(mock_entry.subentries))
    assert [e.data for e in events] == [
        {
            "entry_id": mock_entry.entry_id,
            "from_number": MOM,
            "content": "Turn off the lights",
            "media_url": "",
            "service": "iMessage",
            "message_handle": "BF63384D-A5C4-491A-BDDD-161978DCFD5C",
            "recipient_subentry_id": subentry_id,
            "recipient_name": "Mom",
        }
    ]


async def test_message_from_unknown_sender_fires_event_without_recipient(
    hass: HomeAssistant, client
) -> None:
    events = async_capture_events(hass, EVENT)

    await client.post(URL, json=_payload(from_number="+15550001111"), headers=HEADERS)
    await hass.async_block_till_done()

    assert events[0].data["recipient_subentry_id"] is None
    assert events[0].data["recipient_name"] is None


@pytest.mark.parametrize("headers", [{}, {"sb-signing-secret": "wrong"}])
async def test_wrong_secret_is_rejected_without_event(hass: HomeAssistant, client, headers) -> None:
    events = async_capture_events(hass, EVENT)

    resp = await client.post(URL, json=_payload(), headers=headers)
    await hass.async_block_till_done()

    assert resp.status == 401
    assert events == []


async def test_invalid_json_is_rejected(hass: HomeAssistant, client) -> None:
    resp = await client.post(URL, data="not json", headers=HEADERS)

    assert resp.status == 400


async def test_non_object_json_is_rejected(hass: HomeAssistant, client) -> None:
    resp = await client.post(URL, json=["x"], headers=HEADERS)

    assert resp.status == 400


@pytest.mark.parametrize("overrides", [{"is_outbound": True}, {"group_id": "group-1"}])
async def test_outbound_and_group_messages_are_ignored(
    hass: HomeAssistant, client, overrides
) -> None:
    events = async_capture_events(hass, EVENT)

    resp = await client.post(URL, json=_payload(**overrides), headers=HEADERS)
    await hass.async_block_till_done()

    assert resp.status == 200
    assert events == []


async def test_message_during_setup_is_handled(
    hass: HomeAssistant, mock_entry, mock_api, hass_client_no_auth
) -> None:
    """A redelivery that lands while setup still talks to Sendblue is not lost."""
    events = async_capture_events(hass, EVENT)
    mock_entry.add_to_hass(hass)
    statuses = []
    list_urls = SendblueClient.list_webhook_urls

    async def post_then_list(self):
        client = await hass_client_no_auth()
        resp = await client.post(URL, json=_payload(), headers=HEADERS)
        statuses.append(resp.status)
        return await list_urls(self)

    with patch.object(SendblueClient, "list_webhook_urls", post_then_list):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

    assert statuses == [200]
    assert len(events) == 1


async def test_redelivered_message_is_handled_once(hass: HomeAssistant, client) -> None:
    events = async_capture_events(hass, EVENT)

    await client.post(URL, json=_payload(), headers=HEADERS)
    resp = await client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    assert resp.status == 200
    assert len(events) == 1


SEND_URL = "https://api.sendblue.com/api/send-message"


def _result(speech: str) -> ConversationResult:
    response = intent.IntentResponse(language="en")
    if speech:
        response.async_set_speech(speech)
    return ConversationResult(response=response, conversation_id="ignored")


@pytest.fixture
def converse():
    with patch(
        "custom_components.sendblue.webhook.conversation.async_converse",
        new=AsyncMock(return_value=_result("Lights are off")),
    ) as mock:
        yield mock


@pytest.fixture
async def assist_client(
    hass: HomeAssistant, mock_entry, mock_api, hass_client_no_auth, mom_subentry
):
    mock_entry.add_to_hass(hass)
    subentry = next(iter(mock_entry.subentries.values()))
    hass.config_entries.async_update_subentry(
        mock_entry, subentry, data={**subentry.data, "assist_enabled": True}
    )
    mock_api.post(SEND_URL, status=202, json={"status": "QUEUED"})
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    return await hass_client_no_auth()


def _replies(aioclient_mock) -> list[dict]:
    return [c[2] for c in aioclient_mock.mock_calls if str(c[1]) == SEND_URL]


async def test_assist_reply_is_sent_back_to_sender(
    hass: HomeAssistant, assist_client, mock_entry, mock_api, converse
) -> None:
    await assist_client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    kwargs = converse.call_args.kwargs
    assert kwargs["text"] == "Turn off the lights"
    assert kwargs["conversation_id"] == f"sendblue_{mock_entry.entry_id}_{MOM}"
    assert kwargs["agent_id"] == "conversation.home_assistant"
    assert _replies(mock_api) == [{"number": MOM, "from_number": LINE, "content": "Lights are off"}]


async def test_assist_reply_comes_from_the_line_that_was_texted(
    hass: HomeAssistant, assist_client, mock_api, converse
) -> None:
    await assist_client.post(URL, json=_payload(to_number="+15555550177"), headers=HEADERS)
    await hass.async_block_till_done()

    assert _replies(mock_api)[0]["from_number"] == "+15555550177"


async def test_assist_uses_configured_agent(
    hass: HomeAssistant, assist_client, mock_entry, converse
) -> None:
    hass.config_entries.async_update_entry(
        mock_entry, options={"conversation_agent_id": "conversation.claude"}
    )

    await assist_client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    assert converse.call_args.kwargs["agent_id"] == "conversation.claude"


async def test_assist_is_not_run_when_disabled_for_recipient(
    hass: HomeAssistant, client, converse
) -> None:
    await client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    converse.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        {"from_number": "+15550001111"},
        {"content": "  ", "media_url": "https://cdn.example/a.jpg"},
        {"service": "SMS"},
        {"service": "RCS"},
    ],
)
async def test_assist_is_not_run_for_unknown_sender_empty_text_or_non_imessage(
    hass: HomeAssistant, assist_client, converse, overrides
) -> None:
    await assist_client.post(URL, json=_payload(**overrides), headers=HEADERS)
    await hass.async_block_till_done()

    converse.assert_not_called()


async def test_empty_assist_speech_sends_nothing(
    hass: HomeAssistant, assist_client, mock_api, converse
) -> None:
    converse.return_value = _result("")

    await assist_client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    assert _replies(mock_api) == []


async def test_assist_failure_sends_fixed_error_reply(
    hass: HomeAssistant, assist_client, mock_api, converse
) -> None:
    converse.side_effect = RuntimeError("agent exploded")

    await assist_client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    replies = _replies(mock_api)
    assert len(replies) == 1
    assert "agent exploded" not in replies[0]["content"]


async def test_reply_send_failure_is_logged(
    hass: HomeAssistant,
    mock_entry,
    aioclient_mock,
    hass_client_no_auth,
    converse,
    caplog,
) -> None:
    aioclient_mock.get("https://api.sendblue.com/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get("https://api.sendblue.com/accounts/shared-contacts", json={"contacts": []})
    mock_webhooks(aioclient_mock)
    aioclient_mock.post(SEND_URL, status=500, json={})
    mock_entry.add_to_hass(hass)
    subentry = next(iter(mock_entry.subentries.values()))
    hass.config_entries.async_update_subentry(
        mock_entry, subentry, data={**subentry.data, "assist_enabled": True}
    )
    await hass.config_entries.async_setup(mock_entry.entry_id)
    client = await hass_client_no_auth()

    resp = await client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    assert resp.status == 200
    assert "Cannot send Assist reply" in caplog.text


async def test_assist_defaults_to_preferred_pipeline(
    hass: HomeAssistant, assist_client, converse
) -> None:
    hass.config.components.add("assist_pipeline")
    pipeline = SimpleNamespace(
        conversation_engine="conversation.claude", conversation_language="ko"
    )

    with patch(
        "homeassistant.components.assist_pipeline.async_get_pipeline",
        return_value=pipeline,
    ):
        await assist_client.post(URL, json=_payload(), headers=HEADERS)
        await hass.async_block_till_done()

    assert converse.call_args.kwargs["agent_id"] == "conversation.claude"
    assert converse.call_args.kwargs["language"] == "ko"


async def test_explicit_agent_overrides_preferred_pipeline(
    hass: HomeAssistant, assist_client, mock_entry, converse
) -> None:
    hass.config.components.add("assist_pipeline")
    hass.config_entries.async_update_entry(
        mock_entry, options={"conversation_agent_id": "conversation.other"}
    )

    with patch(
        "homeassistant.components.assist_pipeline.async_get_pipeline",
        return_value=SimpleNamespace(
            conversation_engine="conversation.claude", conversation_language="ko"
        ),
    ):
        await assist_client.post(URL, json=_payload(), headers=HEADERS)
        await hass.async_block_till_done()

    assert converse.call_args.kwargs["agent_id"] == "conversation.other"
    assert converse.call_args.kwargs["language"] == hass.config.language


async def test_pipeline_any_language_falls_back_to_system_language(
    hass: HomeAssistant, assist_client, converse
) -> None:
    hass.config.components.add("assist_pipeline")

    with patch(
        "homeassistant.components.assist_pipeline.async_get_pipeline",
        return_value=SimpleNamespace(
            conversation_engine="conversation.claude", conversation_language="*"
        ),
    ):
        await assist_client.post(URL, json=_payload(), headers=HEADERS)
        await hass.async_block_till_done()

    assert converse.call_args.kwargs["language"] == hass.config.language
