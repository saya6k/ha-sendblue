"""The Sendblue integration."""

from dataclasses import dataclass

import voluptuous as vol
from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import SendblueClient
from .const import (
    ATTR_MEDIA_URL,
    ATTR_SEND_STYLE,
    CONF_API_KEY_ID,
    CONF_API_SECRET_KEY,
    CONF_WEBHOOK_BASE_URL,
    DOMAIN,
    SEND_STYLES,
    SERVICE_SEND_MESSAGE,
)
from .coordinator import SendblueCoordinator
from .webhook import (
    async_delete_remote_webhook,
    async_setup_webhook,
    async_unload_webhook,
)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.NOTIFY]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class SendblueRuntimeData:
    """Objects shared by the platforms of one entry."""

    client: SendblueClient
    coordinator: SendblueCoordinator


type SendblueConfigEntry = ConfigEntry[SendblueRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        entity_domain=NOTIFY_DOMAIN,
        schema={
            vol.Required("message"): cv.string,
            vol.Optional("title"): cv.string,
            vol.Optional(ATTR_MEDIA_URL): cv.url,
            vol.Optional(ATTR_SEND_STYLE): vol.In(SEND_STYLES),
        },
        func="async_send_rich_message",
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SendblueConfigEntry) -> bool:
    client = SendblueClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY_ID],
        entry.data[CONF_API_SECRET_KEY],
    )
    coordinator = SendblueCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = SendblueRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_webhook(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SendblueConfigEntry) -> bool:
    async_unload_webhook(hass, entry)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: SendblueConfigEntry) -> None:
    await async_delete_remote_webhook(hass, entry, entry.data[CONF_WEBHOOK_BASE_URL])
