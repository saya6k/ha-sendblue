"""Shared fixtures for Sendblue tests."""

import pytest
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sendblue.api import BASE_URL
from custom_components.sendblue.const import (
    CONF_API_KEY_ID,
    CONF_API_SECRET_KEY,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    return


@pytest.fixture(autouse=True)
async def setup_homeassistant(hass: HomeAssistant) -> None:
    """Conversation, our dependency, needs the core integration's exposed entities."""
    assert await async_setup_component(hass, "homeassistant", {})


LINE = "+16173011689"
MOM = "+821012345678"


@pytest.fixture
def mock_entry():
    """A configured Sendblue entry (not yet added to hass)."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="key-id",
        data={
            CONF_API_KEY_ID: "key-id",
            CONF_API_SECRET_KEY: "secret",
            CONF_WEBHOOK_BASE_URL: "https://ha.example.com",
            CONF_WEBHOOK_ID: "hook-id",
            CONF_WEBHOOK_SECRET: "hook-secret",
        },
    )


@pytest.fixture
def mock_api(aioclient_mock):
    """Default healthy Sendblue responses; tests override with clear_requests()."""
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get(
        f"{BASE_URL}/accounts/shared-contacts",
        json={"sharedNumber": LINE, "contacts": [{"number": MOM, "verified": True}]},
    )
    return aioclient_mock
