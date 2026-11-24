"""Tests for recipient notify entities and the send_message action."""

import pytest
from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.components.notify import SERVICE_SEND_MESSAGE
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from custom_components.sendblue.api import BASE_URL
from custom_components.sendblue.const import DOMAIN

from .conftest import LINE, MOM

ENTITY_ID = "notify.mom"
SEND_URL = f"{BASE_URL}/api/send-message"


@pytest.fixture
async def setup_entry(hass: HomeAssistant, mock_entry, mock_api):
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    return mock_entry


def _sent_bodies(aioclient_mock) -> list[dict]:
    return [call[2] for call in aioclient_mock.mock_calls if str(call[1]) == SEND_URL]


async def test_recipient_gets_device_and_notify_entity(
    hass: HomeAssistant, setup_entry, device_registry: dr.DeviceRegistry
) -> None:
    state = hass.states.get(ENTITY_ID)

    assert state is not None
    subentry_id = next(iter(setup_entry.subentries))
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, subentry_id), setup_entry.entry_id
    )
    assert device.name == "Mom"


async def test_notify_send_message_joins_title_and_uses_current_line(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    mock_api.post(SEND_URL, status=202, json={"status": "QUEUED"})

    await hass.services.async_call(
        NOTIFY_DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, "message": "Door opened", "title": "Home"},
        blocking=True,
    )

    assert _sent_bodies(mock_api) == [
        {"number": MOM, "from_number": LINE, "content": "Home\nDoor opened"}
    ]


async def test_notify_without_title_sends_message_only(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    mock_api.post(SEND_URL, status=202, json={"status": "QUEUED"})

    await hass.services.async_call(
        NOTIFY_DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, "message": "Door opened"},
        blocking=True,
    )

    assert _sent_bodies(mock_api)[0]["content"] == "Door opened"


async def test_sendblue_action_sends_media_and_style(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    mock_api.post(SEND_URL, status=202, json={"status": "QUEUED"})

    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            "message": "Package arrived",
            "media_url": "https://ha.example.com/local/door.jpg",
            "send_style": "celebration",
        },
        blocking=True,
    )

    body = _sent_bodies(mock_api)[0]
    assert body["media_url"] == "https://ha.example.com/local/door.jpg"
    assert body["send_style"] == "celebration"


async def test_sendblue_action_rejects_unknown_style(hass: HomeAssistant, setup_entry) -> None:
    with pytest.raises(Exception, match="send_style"):
        await hass.services.async_call(
            DOMAIN,
            "send_message",
            {ATTR_ENTITY_ID: ENTITY_ID, "message": "x", "send_style": "explode"},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("status", "body", "translation_key"),
    [
        (
            400,
            {"status": "ERROR", "error_reason": "ContactHasNotBeenVerified"},
            "contact_not_verified",
        ),
        (400, {"status": "ERROR", "error_code": 4009}, "free_plan_limit"),
        (429, {}, "rate_limited"),
        (500, {}, "send_failed"),
    ],
)
async def test_send_errors_are_translated(
    hass: HomeAssistant, setup_entry, mock_api, status, body, translation_key
) -> None:
    mock_api.post(SEND_URL, status=status, json=body)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_ENTITY_ID: ENTITY_ID, "message": "hi"},
            blocking=True,
        )

    assert err.value.translation_key == translation_key


async def test_rejected_credentials_on_send_start_reauth(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    mock_api.post(SEND_URL, status=401, json={})

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            SERVICE_SEND_MESSAGE,
            {ATTR_ENTITY_ID: ENTITY_ID, "message": "hi"},
            blocking=True,
        )
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
