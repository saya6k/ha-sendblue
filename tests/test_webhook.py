"""Tests for the incoming message webhook."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_capture_events

from .conftest import LINE, MOM

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


async def test_message_from_recipient_fires_event(
    hass: HomeAssistant, client, mock_entry
) -> None:
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
async def test_wrong_secret_is_rejected_without_event(
    hass: HomeAssistant, client, headers
) -> None:
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


async def test_redelivered_message_is_handled_once(hass: HomeAssistant, client) -> None:
    events = async_capture_events(hass, EVENT)

    await client.post(URL, json=_payload(), headers=HEADERS)
    resp = await client.post(URL, json=_payload(), headers=HEADERS)
    await hass.async_block_till_done()

    assert resp.status == 200
    assert len(events) == 1
