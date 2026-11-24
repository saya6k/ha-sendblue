"""The Sendblue integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SendblueClient
from .const import CONF_API_KEY_ID, CONF_API_SECRET_KEY

PLATFORMS: list[str] = []


@dataclass
class SendblueRuntimeData:
    """Objects shared by the platforms of one entry."""

    client: SendblueClient


type SendblueConfigEntry = ConfigEntry[SendblueRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SendblueConfigEntry) -> bool:
    client = SendblueClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY_ID],
        entry.data[CONF_API_SECRET_KEY],
    )
    entry.runtime_data = SendblueRuntimeData(client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SendblueConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
