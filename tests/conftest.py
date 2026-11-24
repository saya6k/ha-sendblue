"""Shared fixtures for Sendblue tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp.resolver import AsyncResolver
from aiohttp.test_utils import TestClient, TestServer
from homeassistant import core as ha
from homeassistant import loader
from homeassistant.components.http.server import HomeAssistantHTTP
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import frame
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.sendblue.api import BASE_URL
from custom_components.sendblue.const import (
    CONF_API_KEY_ID,
    CONF_API_SECRET_KEY,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
)
from tests.vendor.aiohttp_mock import AiohttpClientMocker, mock_aiohttp_client
from tests.vendor.ha_common import MockConfigEntry, async_test_home_assistant

LINE = "+15555550100"
MOM = "+821012345678"
WEBHOOKS_URL = f"{BASE_URL}/api/account/webhooks"


@pytest.fixture(autouse=True)
async def mock_zeroconf_resolver() -> AsyncGenerator[None]:
    """Avoid real DNS/zeroconf resolution in tests."""
    with patch(
        "homeassistant.helpers.aiohttp_client._async_make_resolver",
        return_value=AsyncResolver(),
    ):
        yield


@pytest.fixture(autouse=True)
def reset_hass_threading_local_object() -> Generator[None]:
    """Reset the _Hass threading.local object for every test (as HA core's conftest does).

    Otherwise it keeps the last test's hass alive until interpreter shutdown,
    where tearing down its config entries' cached orjson Fragments segfaults.
    """
    yield
    ha._hass.__dict__.clear()


@pytest.fixture(autouse=True)
def mock_http_server() -> Generator[None]:
    """Keep the http component (a webhook dependency) from binding a real port."""
    with (
        patch.object(HomeAssistantHTTP, "async_bind", AsyncMock()),
        patch.object(HomeAssistantHTTP, "start", AsyncMock()),
        patch.object(HomeAssistantHTTP, "stop", AsyncMock()),
    ):
        yield


@pytest.fixture
async def hass(tmp_path) -> AsyncGenerator[HomeAssistant]:
    """Create a test instance of Home Assistant (vendored harness, see tests/vendor/)."""
    async with async_test_home_assistant(
        asyncio.get_running_loop(), config_dir=str(tmp_path)
    ) as test_hass:
        # HA core's own `hass` fixture does this; without it any `frame.report_usage`
        # call reached during a test raises RuntimeError("Frame helper not set up").
        frame.async_setup(test_hass)
        yield test_hass
        await test_hass.async_stop(force=True)
        frame.async_setup(None)


@pytest.fixture
def aioclient_mock() -> Generator[AiohttpClientMocker]:
    """Fixture to mock aioclient calls."""
    with mock_aiohttp_client() as mock_session:
        yield mock_session


@pytest.fixture
def enable_custom_integrations(hass: HomeAssistant) -> None:
    """Enable custom integrations defined in custom_components/."""
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of the sendblue custom integration in tests."""


@pytest.fixture(autouse=True)
async def setup_homeassistant(hass: HomeAssistant) -> None:
    """Conversation, our dependency, needs the core integration's exposed entities."""
    assert await async_setup_component(hass, "homeassistant", {})


@pytest.fixture
async def hass_client_no_auth(
    hass: HomeAssistant,
) -> AsyncGenerator[Callable[[], Awaitable[TestClient]]]:
    """Unauthenticated client for HA's http app, served on a local test server."""
    clients: list[TestClient] = []

    async def create() -> TestClient:
        client = TestClient(TestServer(hass.http.app))
        await client.start_server()
        clients.append(client)
        return client

    yield create
    for client in clients:
        await client.close()


@pytest.fixture
def issue_registry(hass: HomeAssistant) -> ir.IssueRegistry:
    return ir.async_get(hass)


@pytest.fixture
def device_registry(hass: HomeAssistant) -> dr.DeviceRegistry:
    return dr.async_get(hass)


@pytest.fixture
def mom_subentry() -> ConfigSubentryData:
    return ConfigSubentryData(
        data={"address": MOM, "assist_enabled": False},
        subentry_type="recipient",
        title="Mom",
        unique_id=MOM,
    )


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


def mock_webhooks(aioclient_mock: AiohttpClientMocker, existing: list | None = None) -> None:
    """Accept webhook list/add/delete calls."""
    aioclient_mock.get(
        WEBHOOKS_URL,
        json={"status": "OK", "webhooks": {"receive": existing or []}},
    )
    aioclient_mock.post(WEBHOOKS_URL, json={"status": "OK"})
    aioclient_mock.delete(WEBHOOKS_URL, json={"status": "OK"})


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Healthy Sendblue responses for a full entry setup."""
    mock_webhooks(aioclient_mock)
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get(
        f"{BASE_URL}/accounts/shared-contacts",
        json={"sharedNumber": LINE, "contacts": [{"number": MOM, "verified": True}]},
    )
    return aioclient_mock
