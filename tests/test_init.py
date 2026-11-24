"""Tests for Sendblue entry setup, webhook registration, unload and removal."""

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.sendblue.api import BASE_URL, SendblueClient
from custom_components.sendblue.const import DOMAIN

from .conftest import LINE, WEBHOOKS_URL, mock_webhooks

HOOK_URL = "https://ha.example.com/api/webhook/hook-id"


def _calls(aioclient_mock, method: str, url: str) -> list:
    return [
        c
        for c in aioclient_mock.mock_calls
        if c[0].lower() == method and str(c[1]) == url
    ]


async def test_setup_and_unload_entry(
    hass: HomeAssistant, mock_entry, mock_api
) -> None:
    mock_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.LOADED
    assert isinstance(mock_entry.runtime_data.client, SendblueClient)
    assert "hook-id" in hass.data[webhook.DOMAIN]

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
    assert "hook-id" not in hass.data[webhook.DOMAIN]


async def test_setup_registers_webhook_with_secret(
    hass: HomeAssistant, mock_entry, mock_api
) -> None:
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)

    posts = _calls(mock_api, "post", WEBHOOKS_URL)
    assert [p[2] for p in posts] == [
        {"webhooks": [{"url": HOOK_URL, "secret": "hook-secret"}], "type": "receive"}
    ]


async def test_setup_skips_registration_when_already_registered(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get(f"{BASE_URL}/accounts/shared-contacts", json={"contacts": []})
    mock_webhooks(aioclient_mock, existing=[{"url": HOOK_URL, "secret": "x"}])
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert _calls(aioclient_mock, "post", WEBHOOKS_URL) == []


async def test_registration_failure_raises_issue_but_entry_loads(
    hass: HomeAssistant, mock_entry, aioclient_mock, issue_registry: ir.IssueRegistry
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get(f"{BASE_URL}/accounts/shared-contacts", json={"contacts": []})
    aioclient_mock.get(WEBHOOKS_URL, status=500, json={})
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert mock_entry.state is ConfigEntryState.LOADED
    assert issue_registry.async_get_issue(
        DOMAIN, f"webhook_registration_failed_{mock_entry.entry_id}"
    )


async def test_successful_registration_clears_previous_issue(
    hass: HomeAssistant, mock_entry, mock_api, issue_registry: ir.IssueRegistry
) -> None:
    mock_entry.add_to_hass(hass)
    issue_id = f"webhook_registration_failed_{mock_entry.entry_id}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="webhook_registration_failed",
    )

    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_removing_entry_deletes_its_webhook(
    hass: HomeAssistant, mock_entry, mock_api
) -> None:
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)

    await hass.config_entries.async_remove(mock_entry.entry_id)

    deletes = _calls(mock_api, "delete", WEBHOOKS_URL)
    assert [d[2] for d in deletes] == [{"webhooks": [HOOK_URL], "type": "receive"}]


async def test_removing_entry_tolerates_api_failure(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    aioclient_mock.delete(WEBHOOKS_URL, status=500, json={})
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.async_remove(mock_entry.entry_id)

    assert result == {"require_restart": False}
