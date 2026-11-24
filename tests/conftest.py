"""Shared fixtures for Sendblue tests."""

import pytest
from homeassistant.config_entries import ConfigSubentryData
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
def mock_entry(mom_subentry: ConfigSubentryData) -> MockConfigEntry:
    """A configured Sendblue entry with one recipient (not yet added to hass)."""
    return MockConfigEntry(
        subentries_data=[mom_subentry],
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


WEBHOOKS_URL = f"{BASE_URL}/api/account/webhooks"


def mock_webhooks(aioclient_mock, existing: list[str] | None = None) -> None:
    """Accept webhook list/add/delete calls."""
    aioclient_mock.get(
        WEBHOOKS_URL,
        json={"status": "OK", "webhooks": {"receive": existing or []}},
    )
    aioclient_mock.post(WEBHOOKS_URL, json={"status": "OK"})
    aioclient_mock.delete(WEBHOOKS_URL, json={"status": "OK"})


@pytest.fixture
def mock_api(aioclient_mock):
    """Healthy Sendblue responses for a full entry setup."""
    mock_webhooks(aioclient_mock)
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get(
        f"{BASE_URL}/accounts/shared-contacts",
        json={"sharedNumber": LINE, "contacts": [{"number": MOM, "verified": True}]},
    )
    return aioclient_mock


@pytest.fixture
def mom_subentry() -> ConfigSubentryData:
    return ConfigSubentryData(
        data={"address": MOM, "assist_enabled": False},
        subentry_type="recipient",
        title="Mom",
        unique_id=MOM,
    )
