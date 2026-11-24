"""Track the current shared line and recipient verification."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SendblueAuthError, SendblueClient, SendblueError
from .const import CONF_LAST_LINE, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class SendblueData:
    """Current line, and verification per number (None if unknown)."""

    from_number: str
    verified: dict[str, bool] | None


class SendblueCoordinator(DataUpdateCoordinator[SendblueData]):
    """Refresh the shared line; free-plan lines can be reassigned."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: SendblueClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=30),
        )
        self.client = client

    async def _async_update_data(self) -> SendblueData:
        try:
            lines = await self.client.get_lines()
        except SendblueAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SendblueError as err:
            raise UpdateFailed(str(err)) from err
        if not lines:
            raise UpdateFailed("Sendblue account has no line")

        # Undocumented endpoint; losing it must not break sending.
        try:
            verified: dict[str, bool] | None = await self.client.get_shared_contacts()
        except SendblueError as err:
            _LOGGER.debug("Cannot read shared-line contacts: %s", err)
            verified = None

        self._track_line(lines[0])
        return SendblueData(from_number=lines[0], verified=verified)

    def _track_line(self, line: str) -> None:
        entry = self.config_entry
        last = entry.data.get(CONF_LAST_LINE)
        if last == line:
            return
        if last is not None:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"line_changed_{entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="line_changed",
                translation_placeholders={"number": line},
            )
        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_LAST_LINE: line}
        )
