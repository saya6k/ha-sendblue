"""Tests for the Sendblue config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.core_config import async_process_ha_core_config
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sendblue.api import SendblueAuthError, SendblueError
from custom_components.sendblue.const import (
    CONF_API_KEY_ID,
    CONF_API_SECRET_KEY,
    CONF_CONVERSATION_AGENT_ID,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
)

USER_INPUT = {
    CONF_API_KEY_ID: "key-id",
    CONF_API_SECRET_KEY: "secret",
    CONF_WEBHOOK_BASE_URL: "https://ha.example.com/",
}


@pytest.fixture
def get_lines():
    with patch(
        "custom_components.sendblue.config_flow.SendblueClient.get_lines",
        new=AsyncMock(return_value=["+16173011689"]),
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.sendblue.async_setup_entry", return_value=True):
        yield


def _entry(**data) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="key-id",
        data={
            CONF_API_KEY_ID: "key-id",
            CONF_API_SECRET_KEY: "secret",
            CONF_WEBHOOK_BASE_URL: "https://ha.example.com",
            CONF_WEBHOOK_ID: "hook",
            CONF_WEBHOOK_SECRET: "hook-secret",
            **data,
        },
    )


async def test_user_flow_creates_entry_with_generated_webhook(
    hass: HomeAssistant, get_lines
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_API_KEY_ID] == "key-id"
    assert data[CONF_WEBHOOK_BASE_URL] == "https://ha.example.com"
    assert len(data[CONF_WEBHOOK_ID]) >= 32
    assert len(data[CONF_WEBHOOK_SECRET]) >= 32
    assert result["result"].unique_id == "key-id"


async def test_user_flow_suggests_external_url(hass: HomeAssistant) -> None:
    await async_process_ha_core_config(
        hass, {"external_url": "https://home.example.com"}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_WEBHOOK_BASE_URL)
    assert key.default() == "https://home.example.com"


@pytest.mark.parametrize(
    ("side_effect", "lines", "error"),
    [
        (SendblueAuthError("no"), None, "invalid_auth"),
        (SendblueError("down"), None, "cannot_connect"),
        (None, [], "no_lines"),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, get_lines, side_effect, lines, error
) -> None:
    get_lines.side_effect = side_effect
    get_lines.return_value = lines
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    get_lines.side_effect = None
    get_lines.return_value = ["+16173011689"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_rejects_non_https_url(hass: HomeAssistant, get_lines) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**USER_INPUT, CONF_WEBHOOK_BASE_URL: "http://ha.local:8123"},
    )

    assert result["errors"] == {CONF_WEBHOOK_BASE_URL: "invalid_url"}
    get_lines.assert_not_called()


async def test_user_flow_aborts_for_same_api_key(
    hass: HomeAssistant, get_lines
) -> None:
    _entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_credentials(hass: HomeAssistant, get_lines) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    get_lines.side_effect = SendblueAuthError("no")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY_ID: "new-id", CONF_API_SECRET_KEY: "bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    get_lines.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY_ID: "new-id", CONF_API_SECRET_KEY: "new"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_SECRET_KEY] == "new"
    assert entry.unique_id == "new-id"
    assert entry.data[CONF_WEBHOOK_ID] == "hook"


async def test_reconfigure_updates_webhook_base_url(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEBHOOK_BASE_URL: "ftp://nope"}
    )
    assert result["errors"] == {CONF_WEBHOOK_BASE_URL: "invalid_url"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEBHOOK_BASE_URL: "https://new.example.com/"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_WEBHOOK_BASE_URL] == "https://new.example.com"


async def test_options_flow_sets_conversation_agent(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CONVERSATION_AGENT_ID: "conversation.home_assistant"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_CONVERSATION_AGENT_ID] == "conversation.home_assistant"
