"""Tests for the line and verification coordinator."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.sendblue.api import BASE_URL
from custom_components.sendblue.const import CONF_LAST_LINE, DOMAIN

from .conftest import LINE, MOM, mock_webhooks


async def test_refresh_exposes_line_and_verification(
    hass: HomeAssistant, mock_entry, mock_api
) -> None:
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)

    data = mock_entry.runtime_data.coordinator.data
    assert data.from_number == LINE
    assert data.verified == {MOM: True}
    assert mock_entry.data[CONF_LAST_LINE] == LINE


async def test_first_line_seen_does_not_raise_issue(
    hass: HomeAssistant, mock_entry, mock_api, issue_registry: ir.IssueRegistry
) -> None:
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert len(issue_registry.issues) == 0


async def test_changed_line_raises_repair_issue(
    hass: HomeAssistant, mock_entry, mock_api, issue_registry: ir.IssueRegistry
) -> None:
    mock_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_entry, data={**mock_entry.data, CONF_LAST_LINE: "+15555550199"}
    )

    await hass.config_entries.async_setup(mock_entry.entry_id)

    issue = issue_registry.async_get_issue(DOMAIN, f"line_changed_{mock_entry.entry_id}")
    assert issue is not None
    assert issue.translation_placeholders == {"number": LINE}
    assert mock_entry.data[CONF_LAST_LINE] == LINE


async def test_contacts_failure_keeps_entry_working(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get(f"{BASE_URL}/accounts/shared-contacts", status=404, json={})
    mock_webhooks(aioclient_mock)
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert mock_entry.state is ConfigEntryState.LOADED
    data = mock_entry.runtime_data.coordinator.data
    assert data.from_number == LINE
    assert data.verified is None


async def test_rejected_credentials_start_reauth(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", status=401, json={})
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_unreachable_api_retries_setup(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", status=500, json={})
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_account_without_lines_retries_setup(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": []})
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_same_line_on_later_refresh_raises_no_issue(
    hass: HomeAssistant, mock_entry, mock_api, issue_registry: ir.IssueRegistry
) -> None:
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)

    await mock_entry.runtime_data.coordinator.async_refresh()

    assert len(issue_registry.issues) == 0
    assert mock_entry.data[CONF_LAST_LINE] == LINE


async def test_malformed_contacts_keeps_entry_working(
    hass: HomeAssistant, mock_entry, aioclient_mock
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/lines", json={"numbers": [LINE]})
    aioclient_mock.get(f"{BASE_URL}/accounts/shared-contacts", json={"contacts": [{"x": 1}]})
    mock_webhooks(aioclient_mock)
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)

    assert mock_entry.state is ConfigEntryState.LOADED
    assert mock_entry.runtime_data.coordinator.data.verified is None
