"""Arrival/departure boards and a diagnostic refresh timestamp."""

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ViaggiaTrenoConfigEntry
from .const import DOMAIN
from .coordinator import StationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViaggiaTrenoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create exactly three entities for each station entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            BoardSensor(coordinator, entry, "arrivi"),
            BoardSensor(coordinator, entry, "partenze"),
            LastRefreshSensor(coordinator, entry),
        ]
    )


class StationEntity(CoordinatorEntity[StationCoordinator], SensorEntity):
    """Entity identity belongs to the entry, so reconfiguration preserves cards."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: StationCoordinator, entry: ViaggiaTrenoConfigEntry, key: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.station_name.title(),
            manufacturer="ViaggiaTreno",
            model="Station monitor",
            configuration_url="http://www.viaggiatreno.it/",
        )


class BoardSensor(StationEntity):
    """The state is a count; the bounded upstream board lives in attributes."""

    _attr_icon = "mdi:train"
    _unrecorded_attributes = frozenset({"trains", "last_refresh"})

    def __init__(
        self,
        coordinator: StationCoordinator,
        entry: ViaggiaTrenoConfigEntry,
        direction: str,
    ) -> None:
        super().__init__(coordinator, entry, direction)
        self.direction = direction

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data[self.direction])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "station_id": self.coordinator.station_id,
            "station_name": self.coordinator.station_name,
            "direction": self.direction,
            "trains": self.coordinator.data[self.direction],
            "last_refresh": self.coordinator.last_success.isoformat(),
            "attribution": "Data provided by ViaggiaTreno / Trenitalia",
        }


class LastRefreshSensor(StationEntity):
    """Retain the last success during outages, rather than masking it as unavailable."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: StationCoordinator, entry: ViaggiaTrenoConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "last_refresh")

    @property
    def available(self) -> bool:
        return self.coordinator.last_success is not None

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"last_update_success": self.coordinator.last_update_success}
