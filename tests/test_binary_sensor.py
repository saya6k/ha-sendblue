"""Tests for the recipient verification binary sensor."""

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.sendblue.api import BASE_URL

from .conftest import LINE, MOM, mock_webhooks

ENTITY_ID = "binary_sensor.mom_verified"


async def _setup(hass: HomeAssistant, entry, aioclient_mock, contacts) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get(f"{BASE_URL}/accounts/shared-contacts", **contacts)
    mock_webhooks(aioclient_mock)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_verified_recipient_is_on(hass: HomeAssistant, mock_entry, aioclient_mock) -> None:
    await _setup(
        hass,
        mock_entry,
        aioclient_mock,
        {"json": {"contacts": [{"number": MOM, "verified": True}]}},
    )

    assert hass.states.get(ENTITY_ID).state == STATE_ON


async def test_unverified_or_missing_recipient_is_off(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    await _setup(
        hass,
        mock_entry,
        aioclient_mock,
        {"json": {"contacts": [{"number": "+8201012345678", "verified": True}]}},
    )

    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_unknown_verification_is_unavailable(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    await _setup(hass, mock_entry, aioclient_mock, {"status": 404, "json": {}})

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
