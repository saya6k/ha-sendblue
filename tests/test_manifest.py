"""Smoke test that the integration package loads."""

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from custom_components.sendblue.const import DOMAIN


async def test_integration_is_discoverable(hass: HomeAssistant) -> None:
    integration = await async_get_integration(hass, DOMAIN)

    assert integration.domain == DOMAIN
    assert integration.config_flow is True
