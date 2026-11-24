"""Whether each recipient has verified with the shared line."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SendblueConfigEntry
from .const import CONF_ADDRESS, SUBENTRY_RECIPIENT
from .coordinator import SendblueCoordinator
from .notify import recipient_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SendblueConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_RECIPIENT:
            async_add_entities(
                [VerifiedBinarySensor(coordinator, subentry)],
                config_subentry_id=subentry.subentry_id,
            )


class VerifiedBinarySensor(CoordinatorEntity[SendblueCoordinator], BinarySensorEntity):
    """On once the recipient has texted the shared line."""

    _attr_has_entity_name = True
    _attr_translation_key = "verified"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SendblueCoordinator, subentry: ConfigSubentry) -> None:
        super().__init__(coordinator)
        self._address: str = subentry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{subentry.subentry_id}_verified"
        self._attr_device_info = recipient_device_info(subentry)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.verified is not None

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data.verified or {}).get(self._address))
