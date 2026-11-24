"""Tests for Sendblue entry setup and unload."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.sendblue.api import SendblueClient


async def test_setup_and_unload_entry(
    hass: HomeAssistant, mock_entry, mock_api
) -> None:
    mock_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.LOADED
    assert isinstance(mock_entry.runtime_data.client, SendblueClient)

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
