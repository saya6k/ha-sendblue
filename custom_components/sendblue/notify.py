"""Notify entities, one per recipient."""

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SendblueConfigEntry
from .api import (
    SendblueAuthError,
    SendblueContactNotVerified,
    SendblueError,
    SendblueFreePlanLimit,
    SendblueRateLimited,
)
from .const import CONF_ADDRESS, DOMAIN, SUBENTRY_RECIPIENT


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SendblueConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_RECIPIENT:
            async_add_entities(
                [SendblueNotifyEntity(entry, subentry)],
                config_subentry_id=subentry.subentry_id,
            )


def recipient_device_info(subentry: ConfigSubentry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, subentry.subentry_id)},
        name=subentry.title,
        manufacturer="Sendblue",
        entry_type=DeviceEntryType.SERVICE,
    )


class SendblueNotifyEntity(NotifyEntity):
    """Send iMessages to one recipient."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: SendblueConfigEntry, subentry: ConfigSubentry) -> None:
        self._entry = entry
        self._address: str = subentry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{subentry.subentry_id}_notify"
        self._attr_device_info = recipient_device_info(subentry)

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        await self.async_send_rich_message(message, title)

    async def async_send_rich_message(
        self,
        message: str,
        title: str | None = None,
        media_url: str | None = None,
        send_style: str | None = None,
    ) -> None:
        """Back the notify action and sendblue.send_message."""
        runtime = self._entry.runtime_data
        content = f"{title}\n{message}" if title else message
        try:
            await runtime.client.send_message(
                self._address,
                runtime.coordinator.data.from_number,
                content=content,
                media_url=media_url,
                send_style=send_style,
            )
        except SendblueAuthError as err:
            self._entry.async_start_reauth(self.hass)
            raise _error("auth_failed") from err
        except SendblueContactNotVerified as err:
            await runtime.coordinator.async_request_refresh()
            raise _error(
                "contact_not_verified",
                {"number": runtime.coordinator.data.from_number},
            ) from err
        except SendblueFreePlanLimit as err:
            raise _error("free_plan_limit") from err
        except SendblueRateLimited as err:
            raise _error("rate_limited") from err
        except SendblueError as err:
            # The shared line may have moved; refresh before the next try.
            await runtime.coordinator.async_request_refresh()
            raise _error("send_failed", {"error": str(err)}) from err


def _error(key: str, placeholders: dict[str, str] | None = None) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders,
    )
