from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENTITY_NUMBER
from .coordinator import ModbusConfigEntry, ModbusCoordinator
from .entity import ModbusEntity, enum_or_none
from .register import RegisterDef

async def async_setup_entry(
    hass: HomeAssistant, entry: ModbusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ModbusNumber(coordinator, entry, reg)
        for reg in coordinator.registers
        if reg.entity_type == ENTITY_NUMBER
    )

class ModbusNumber(ModbusEntity, NumberEntity):
    def __init__(self, coordinator: ModbusCoordinator, entry: ModbusConfigEntry, reg: RegisterDef) -> None:
        super().__init__(coordinator, entry, reg)
        self._attr_native_unit_of_measurement = reg.unit
        self._attr_native_min_value = reg.min_value
        self._attr_native_max_value = reg.max_value
        self._attr_native_step = reg.step
        self._attr_device_class = enum_or_none(NumberDeviceClass, reg.device_class)

    @property
    def native_value(self) -> float | None:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write(self._reg, value)
        data = dict(self.coordinator.data or {})
        data[self._reg.unique_id] = value
        self.coordinator.async_set_updated_data(data)
