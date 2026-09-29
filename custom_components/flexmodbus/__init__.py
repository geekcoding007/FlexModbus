from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .connection import create_client
from . import log_filter
from .const import CONF_FRAMER, CONF_SUPPRESS_LOG_NOISE, FRAMER_RTU
from .coordinator import ModbusConfigEntry, ModbusCoordinator
from .register import RegisterDef, parse_registers

PLATFORMS = [Platform.SENSOR, Platform.NUMBER]

def _remove_stale_entities(hass: HomeAssistant, entry: ModbusConfigEntry, registers: list[RegisterDef]) -> None:
    active = {reg.unique_id for reg in registers}
    ent_reg = er.async_get(hass)
    for registered in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if registered.unique_id not in active:
            ent_reg.async_remove(registered.entity_id)

async def async_setup_entry(hass: HomeAssistant, entry: ModbusConfigEntry) -> bool:
    registers = parse_registers(entry)
    _remove_stale_entities(hass, entry, registers)

    client = create_client(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_FRAMER, FRAMER_RTU),
    )
    entry.async_on_unload(client.close)

    if entry.data.get(CONF_SUPPRESS_LOG_NOISE, False):
        log_filter.enable(entry.entry_id)
        entry.async_on_unload(lambda: log_filter.disable(entry.entry_id))

    coordinator = ModbusCoordinator(hass, entry, client, registers)
    entry.async_on_unload(coordinator.async_shutdown_idle_timer)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True

async def _async_update_listener(hass: HomeAssistant, entry: ModbusConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ModbusConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
