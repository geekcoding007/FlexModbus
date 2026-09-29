from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENTITY_SENSOR
from .coordinator import ModbusConfigEntry, ModbusCoordinator
from .entity import ModbusEntity, enum_or_none
from .register import RegisterDef

async def async_setup_entry(
    hass: HomeAssistant, entry: ModbusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ModbusSensor(coordinator, entry, reg)
        for reg in coordinator.registers
        if reg.entity_type == ENTITY_SENSOR
    )

class ModbusSensor(ModbusEntity, SensorEntity):
    def __init__(self, coordinator: ModbusCoordinator, entry: ModbusConfigEntry, reg: RegisterDef) -> None:
        super().__init__(coordinator, entry, reg)
        if reg.is_enum:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = sorted(set(reg.value_map.values()))
        elif reg.is_bitfield:
            pass
        else:
            self._attr_native_unit_of_measurement = reg.unit
            self._attr_device_class = enum_or_none(SensorDeviceClass, reg.device_class)
            self._attr_state_class = enum_or_none(SensorStateClass, reg.state_class)

    @property
    def native_value(self) -> float | str | None:
        return self._value
