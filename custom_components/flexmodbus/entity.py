from __future__ import annotations

from enum import Enum
from typing import TypeVar

from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ModbusConfigEntry, ModbusCoordinator
from .register import RegisterDef

_E = TypeVar("_E", bound=Enum)

def enum_or_none(enum_cls: type[_E], value: str | None) -> _E | None:
    if not value:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return None

class ModbusEntity(CoordinatorEntity[ModbusCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ModbusCoordinator, entry: ModbusConfigEntry, reg: RegisterDef) -> None:
        super().__init__(coordinator)
        self._reg = reg
        self._attr_unique_id = reg.unique_id
        self._attr_name = reg.name
        self._attr_entity_category = enum_or_none(EntityCategory, reg.entity_category)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, entry.title),
            manufacturer=MANUFACTURER,
            model="Modbus TCP",
        )

    @property
    def _value(self) -> float | str | None:
        return (self.coordinator.data or {}).get(self._reg.unique_id)

    @property
    def available(self) -> bool:
        return super().available and self._value is not None
