from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENTITY_SWITCH
from .coordinator import ModbusConfigEntry, ModbusCoordinator
from .entity import ModbusEntity
from .register import RegisterDef

async def async_setup_entry(
    hass: HomeAssistant, entry: ModbusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ModbusSwitch(coordinator, entry, reg)
        for reg in coordinator.registers
        if reg.entity_type == ENTITY_SWITCH
    )

class ModbusSwitch(ModbusEntity, SwitchEntity):
    def __init__(self, coordinator: ModbusCoordinator, entry: ModbusConfigEntry, reg: RegisterDef) -> None:
        super().__init__(coordinator, entry, reg)

    @property
    def is_on(self) -> bool | None:
        value = self._value
        if value is None:
            return None
        return int(value) == self._reg.on_value

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set(self._reg.on_value)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set(self._reg.off_value)

    async def _async_set(self, code: int) -> None:
        await self.coordinator.async_write(self._reg, code)
        data = dict(self.coordinator.data or {})
        data[self._reg.unique_id] = code
        self.coordinator.async_set_updated_data(data)
