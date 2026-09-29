from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_UNIT_OF_MEASUREMENT,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from pymodbus.exceptions import ModbusException

from .connection import create_client

from .const import (
    BYTE_ORDERS,
    CONF_BYTE_ORDER,
    CONF_DATA_TYPE,
    CONF_ENT_TYPE,
    CONF_ENTITY_CATEGORY,
    CONF_FRAMER,
    CONF_IDLE_CLOSE_SECONDS,
    CONF_REQUEST_DELAY,
    CONF_SCAN_INTERVAL,
    CONF_MAX,
    CONF_MIN,
    CONF_MULTIPLIER,
    CONF_OFFSET,
    CONF_REG_ADDRESS,
    CONF_REG_SLAVE,
    CONF_REG_TYPE,
    CONF_REGISTERS,
    CONF_STATE_CLASS,
    CONF_STEP,
    CONF_SUPPRESS_LOG_NOISE,
    CONF_VALUE_MAP,
    CONF_BIT_LABELS,
    CONNECT_TIMEOUT,
    DATA_TYPES,
    DEFAULT_IDLE_CLOSE_SECONDS,
    DEFAULT_REQUEST_DELAY,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_CLASSES,
    DEVICE_CLASSES_WITHOUT_UNIT,
    DOMAIN,
    ENTITY_NUMBER,
    ENTITY_SENSOR,
    ENTITY_CATEGORIES,
    ENTITY_TYPES,
    FRAMER_RTU,
    FRAMER_SOCKET,
    FRAMERS,
    MAX_IDLE_CLOSE_SECONDS,
    MAX_REQUEST_DELAY,
    MAX_SCAN_INTERVAL,
    MIN_IDLE_CLOSE_SECONDS,
    MIN_REQUEST_DELAY,
    MIN_SCAN_INTERVAL,
    REG_HOLDING,
    REG_INPUT,
    REGISTER_TYPES,
    STATE_CLASSES,
)
from .register import get_raw_registers, is_string_type, normalize_byte_order, parse_register
from .yaml_import import Skipped, convert_yaml

async def _async_test_connection(host: str, port: int, framer: str) -> bool:
    client = create_client(host, port, framer, retries=0)
    try:
        await client.connect()
        return bool(client.connected)
    except (ModbusException, OSError, TimeoutError):
        return False
    finally:
        client.close()

def _select(options: list[str], translation_key: str) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            translation_key=translation_key,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )

def _connection_schema(defaults: dict[str, Any], with_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "ModbusSlave"))] = str
    fields[vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "192.168.1.100"))] = str
    fields[vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, 502))] = vol.All(
        vol.Coerce(int), vol.Range(min=1, max=65535)
    )
    fields[vol.Required(CONF_FRAMER, default=defaults.get(CONF_FRAMER, FRAMER_SOCKET))] = _select(
        FRAMERS, "framer"
    )
    fields[
        vol.Required(CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    ] = NumberSelector(
        NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="s")
    )
    fields[
        vol.Required(CONF_REQUEST_DELAY, default=defaults.get(CONF_REQUEST_DELAY, DEFAULT_REQUEST_DELAY))
    ] = NumberSelector(
        NumberSelectorConfig(min=MIN_REQUEST_DELAY, max=MAX_REQUEST_DELAY, step=10, mode=NumberSelectorMode.BOX, unit_of_measurement="ms")
    )
    fields[
        vol.Required(
            CONF_IDLE_CLOSE_SECONDS, default=defaults.get(CONF_IDLE_CLOSE_SECONDS, DEFAULT_IDLE_CLOSE_SECONDS)
        )
    ] = NumberSelector(
        NumberSelectorConfig(
            min=MIN_IDLE_CLOSE_SECONDS, max=MAX_IDLE_CLOSE_SECONDS, step=1,
            mode=NumberSelectorMode.BOX, unit_of_measurement="s",
        )
    )
    fields[
        vol.Required(CONF_SUPPRESS_LOG_NOISE, default=defaults.get(CONF_SUPPRESS_LOG_NOISE, False))
    ] = BooleanSelector()
    return vol.Schema(fields)

class ModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        defaults = user_input or {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            framer = user_input[CONF_FRAMER]
            name = user_input[CONF_NAME].strip()

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            if not name:
                errors[CONF_NAME] = "name_required"
            elif not await _async_test_connection(host, port, framer):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_FRAMER: framer,
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_REQUEST_DELAY: int(user_input[CONF_REQUEST_DELAY]),
                        CONF_IDLE_CLOSE_SECONDS: int(user_input[CONF_IDLE_CLOSE_SECONDS]),
                        CONF_SUPPRESS_LOG_NOISE: bool(user_input[CONF_SUPPRESS_LOG_NOISE]),
                    },
                    options={CONF_REGISTERS: []},
                )

        return self.async_show_form(
            step_id="user", data_schema=_connection_schema(defaults, with_name=True), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            framer = user_input[CONF_FRAMER]
            new_unique_id = f"{host}:{port}"

            if any(
                other.entry_id != entry.entry_id and other.unique_id == new_unique_id
                for other in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")

            if not await _async_test_connection(host, port, framer):
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    unique_id=new_unique_id,
                    data={
                        **entry.data,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_FRAMER: framer,
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_REQUEST_DELAY: int(user_input[CONF_REQUEST_DELAY]),
                        CONF_IDLE_CLOSE_SECONDS: int(user_input[CONF_IDLE_CLOSE_SECONDS]),
                        CONF_SUPPRESS_LOG_NOISE: bool(user_input[CONF_SUPPRESS_LOG_NOISE]),
                    },
                )
                return self.async_abort(reason="reconfigure_successful")

        defaults = user_input or {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_PORT: entry.data[CONF_PORT],
            CONF_FRAMER: entry.data.get(CONF_FRAMER, FRAMER_RTU),
            CONF_SCAN_INTERVAL: entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            CONF_REQUEST_DELAY: entry.data.get(CONF_REQUEST_DELAY, DEFAULT_REQUEST_DELAY),
            CONF_IDLE_CLOSE_SECONDS: entry.data.get(CONF_IDLE_CLOSE_SECONDS, DEFAULT_IDLE_CLOSE_SECONDS),
            CONF_SUPPRESS_LOG_NOISE: entry.data.get(CONF_SUPPRESS_LOG_NOISE, False),
        }
        return self.async_show_form(
            step_id="reconfigure", data_schema=_connection_schema(defaults, with_name=False), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> ModbusOptionsFlowHandler:
        return ModbusOptionsFlowHandler()

def _format_value_map(value_map: dict[str, str] | str | None) -> str:
    if not value_map:
        return ""
    if isinstance(value_map, str):
        return value_map
    return "\n".join(f"{k}: {v}" for k, v in value_map.items())


def _parse_value_map(text: str) -> tuple[dict[str, str] | None, str | None]:
    text = (text or "").strip()
    if not text:
        return None, None
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        sep = ":" if ":" in line else ("=" if "=" in line else None)
        if sep is None:
            return None, "value_map_format"
        raw_code, _, label = line.partition(sep)
        raw_code = raw_code.strip()
        label = label.strip()
        try:
            code = int(raw_code)
        except ValueError:
            return None, "value_map_format"
        if not label:
            return None, "value_map_format"
        key = str(code)
        if key in result:
            return None, "value_map_duplicate"
        result[key] = label
    return (result or None), None


def _format_bit_labels(bit_labels: dict[str, str] | str | None) -> str:
    if not bit_labels:
        return ""
    if isinstance(bit_labels, str):
        return bit_labels
    return "\n".join(f"{k}: {v}" for k, v in bit_labels.items())


def _parse_bit_labels(text: str) -> tuple[dict[str, str] | None, str | None]:
    text = (text or "").strip()
    if not text:
        return None, None
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        sep = ":" if ":" in line else ("=" if "=" in line else None)
        if sep is None:
            return None, "bit_labels_format"
        raw_bit, _, label = line.partition(sep)
        raw_bit = raw_bit.strip()
        label = label.strip()
        try:
            bit = int(raw_bit)
        except ValueError:
            return None, "bit_labels_format"
        if bit < 0 or not label:
            return None, "bit_labels_format"
        key = str(bit)
        if key in result:
            return None, "bit_labels_duplicate"
        result[key] = label
    return (result or None), None


def _register_schema(defaults: dict[str, Any]) -> vol.Schema:
    d = defaults
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
            vol.Required(CONF_ENT_TYPE, default=d.get(CONF_ENT_TYPE, ENTITY_SENSOR)): _select(
                ENTITY_TYPES, "entity_type"
            ),
            vol.Required(CONF_ENTITY_CATEGORY, default=d.get(CONF_ENTITY_CATEGORY, "none")): _select(
                ENTITY_CATEGORIES, "entity_category"
            ),
            vol.Required(CONF_DEVICE_CLASS, default=d.get(CONF_DEVICE_CLASS, "none")): _select(
                DEVICE_CLASSES, "device_class"
            ),
            vol.Required(CONF_STATE_CLASS, default=d.get(CONF_STATE_CLASS, "none")): _select(
                STATE_CLASSES, "state_class"
            ),
            vol.Required(CONF_REG_TYPE, default=d.get(CONF_REG_TYPE, REG_HOLDING)): _select(
                REGISTER_TYPES, "register_type"
            ),
            vol.Required(CONF_REG_ADDRESS, default=d.get(CONF_REG_ADDRESS, 1)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65536)
            ),
            vol.Required(CONF_REG_SLAVE, default=d.get(CONF_REG_SLAVE, 1)): NumberSelector(
                NumberSelectorConfig(min=0, max=255, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_DATA_TYPE, default=d.get(CONF_DATA_TYPE, "uint16")): _select(
                DATA_TYPES, "data_type"
            ),
            vol.Required(
                CONF_BYTE_ORDER, default=normalize_byte_order(d.get(CONF_BYTE_ORDER))
            ): _select(BYTE_ORDERS, "byte_order"),
            vol.Optional(CONF_UNIT_OF_MEASUREMENT, default=d.get(CONF_UNIT_OF_MEASUREMENT, "")): str,
            vol.Required(CONF_MULTIPLIER, default=d.get(CONF_MULTIPLIER, 1.0)): vol.Coerce(float),
            vol.Required(CONF_OFFSET, default=d.get(CONF_OFFSET, 0.0)): vol.Coerce(float),
            vol.Required(CONF_MIN, default=d.get(CONF_MIN, 0.0)): vol.Coerce(float),
            vol.Required(CONF_MAX, default=d.get(CONF_MAX, 100.0)): vol.Coerce(float),
            vol.Required(CONF_STEP, default=d.get(CONF_STEP, 1.0)): vol.Coerce(float),
            vol.Optional(
                CONF_VALUE_MAP, default=_format_value_map(d.get(CONF_VALUE_MAP))
            ): TextSelector(TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)),
            vol.Optional(
                CONF_BIT_LABELS, default=_format_bit_labels(d.get(CONF_BIT_LABELS))
            ): TextSelector(TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)),
        }
    )

def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    reg = dict(user_input)
    reg[CONF_NAME] = reg[CONF_NAME].strip()
    reg[CONF_UNIT_OF_MEASUREMENT] = (reg.get(CONF_UNIT_OF_MEASUREMENT) or "").strip()
    reg[CONF_BYTE_ORDER] = normalize_byte_order(reg.get(CONF_BYTE_ORDER))
    reg[CONF_REG_SLAVE] = int(reg[CONF_REG_SLAVE])
    reg[CONF_REG_ADDRESS] = int(reg[CONF_REG_ADDRESS])
    if reg[CONF_ENT_TYPE] == ENTITY_NUMBER:
        reg[CONF_REG_TYPE] = REG_HOLDING
    if is_string_type(reg[CONF_DATA_TYPE]):
        reg[CONF_DEVICE_CLASS] = "none"
        reg[CONF_STATE_CLASS] = "none"
        reg[CONF_UNIT_OF_MEASUREMENT] = ""
    value_map, _ = _parse_value_map(reg.get(CONF_VALUE_MAP, ""))
    reg[CONF_VALUE_MAP] = value_map or {}
    if value_map:
        reg[CONF_DEVICE_CLASS] = "none"
        reg[CONF_STATE_CLASS] = "none"
        reg[CONF_UNIT_OF_MEASUREMENT] = ""
    bit_labels, _ = _parse_bit_labels(reg.get(CONF_BIT_LABELS, ""))
    reg[CONF_BIT_LABELS] = bit_labels or {}
    if bit_labels:
        reg[CONF_DEVICE_CLASS] = "none"
        reg[CONF_STATE_CLASS] = "none"
        reg[CONF_UNIT_OF_MEASUREMENT] = ""
    return reg

def _validate(
    user_input: dict[str, Any],
    registers: list[dict[str, Any]],
    skip_index: int | None,
    framer: str = FRAMER_SOCKET,
) -> dict[str, str]:
    errors: dict[str, str] = {}

    if not user_input[CONF_NAME].strip():
        errors[CONF_NAME] = "name_required"
    is_text = is_string_type(user_input[CONF_DATA_TYPE])
    if is_text and user_input[CONF_ENT_TYPE] == ENTITY_NUMBER:
        errors[CONF_DATA_TYPE] = "string_not_number"

    value_map, value_map_error = _parse_value_map(user_input.get(CONF_VALUE_MAP, ""))
    if value_map_error:
        errors[CONF_VALUE_MAP] = value_map_error
    elif value_map:
        if user_input[CONF_ENT_TYPE] == ENTITY_NUMBER:
            errors[CONF_VALUE_MAP] = "value_map_not_number"
        elif is_text or user_input[CONF_DATA_TYPE] == "float32":
            errors[CONF_VALUE_MAP] = "value_map_unsupported_datatype"

    bit_labels, bit_labels_error = _parse_bit_labels(user_input.get(CONF_BIT_LABELS, ""))
    if bit_labels_error:
        errors[CONF_BIT_LABELS] = bit_labels_error
    elif bit_labels:
        if user_input[CONF_ENT_TYPE] == ENTITY_NUMBER:
            errors[CONF_BIT_LABELS] = "bit_labels_not_number"
        elif user_input[CONF_DATA_TYPE] not in ("uint16", "uint32"):
            errors[CONF_BIT_LABELS] = "bit_labels_unsupported_datatype"
        elif value_map:
            errors[CONF_BIT_LABELS] = "bit_labels_and_value_map"
        else:
            width = 32 if user_input[CONF_DATA_TYPE] == "uint32" else 16
            if any(not (0 <= int(k) < width) for k in bit_labels):
                errors[CONF_BIT_LABELS] = "bit_labels_out_of_range"
    if framer == FRAMER_RTU and user_input[CONF_REG_SLAVE] == 0:
        errors[CONF_REG_SLAVE] = "slave_broadcast"
    if user_input[CONF_ENTITY_CATEGORY] == "config" and user_input[CONF_ENT_TYPE] == ENTITY_SENSOR:
        errors[CONF_ENTITY_CATEGORY] = "config_not_for_sensor"
    if user_input[CONF_MULTIPLIER] == 0:
        errors[CONF_MULTIPLIER] = "invalid_multiplier"
    if user_input[CONF_ENT_TYPE] == ENTITY_NUMBER:
        if user_input[CONF_REG_TYPE] == REG_INPUT:
            errors[CONF_REG_TYPE] = "input_not_writable"
        if user_input[CONF_MIN] >= user_input[CONF_MAX]:
            errors[CONF_MAX] = "min_max"
    if (
        not is_text
        and not value_map
        and not bit_labels
        and user_input[CONF_DEVICE_CLASS] not in DEVICE_CLASSES_WITHOUT_UNIT
        and not (user_input.get(CONF_UNIT_OF_MEASUREMENT) or "").strip()
    ):
        errors[CONF_UNIT_OF_MEASUREMENT] = "unit_required"

    if not errors:
        new_id = parse_register("x", _clean(user_input)).unique_id
        for index, existing in enumerate(registers):
            if index == skip_index:
                continue
            try:
                if parse_register("x", existing).unique_id == new_id:
                    errors["base"] = "duplicate_register"
                    break
            except (KeyError, ValueError, TypeError):
                continue
    return errors

def _register_label(reg: dict[str, Any]) -> str:
    return (
        f"[{reg.get(CONF_ENT_TYPE, ENTITY_SENSOR)}] {reg.get(CONF_NAME, '?')} "
        f"(slave {reg.get(CONF_REG_SLAVE, '?')}, reg {reg.get(CONF_REG_ADDRESS, '?')})"
    )

def _register_picker(registers: list[dict[str, Any]]) -> vol.Schema:
    options = [SelectOptionDict(value=str(i), label=_register_label(r)) for i, r in enumerate(registers)]
    return vol.Schema(
        {
            vol.Required("register_index"): SelectSelector(
                SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
            )
        }
    )


def _yaml_import_schema(default_text: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("yaml_text", default=default_text): TextSelector(
                TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)
            )
        }
    )

class ModbusOptionsFlowHandler(OptionsFlow):
    def __init__(self) -> None:
        self._edit_index = 0
        self._import_result = None

    def _registers(self) -> list[dict[str, Any]]:
        return get_raw_registers(self.config_entry)

    def _framer(self) -> str:
        return self.config_entry.data.get(CONF_FRAMER, FRAMER_RTU)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_register", "select_edit", "select_delete", "import_yaml"],
        )

    async def async_step_add_register(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            registers = self._registers()
            errors = _validate(user_input, registers, None, self._framer())
            if not errors:
                registers.append(_clean(user_input))
                return self.async_create_entry(title="", data={CONF_REGISTERS: registers})

        return self.async_show_form(
            step_id="add_register",
            data_schema=_register_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_select_edit(self, user_input: dict[str, Any] | None = None):
        registers = self._registers()
        if not registers:
            return self.async_abort(reason="no_registers")

        if user_input is not None:
            self._edit_index = int(user_input["register_index"])
            return await self.async_step_edit_register()

        return self.async_show_form(step_id="select_edit", data_schema=_register_picker(registers))

    async def async_step_edit_register(self, user_input: dict[str, Any] | None = None):
        registers = self._registers()
        if not 0 <= self._edit_index < len(registers):
            return self.async_abort(reason="no_registers")

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input, registers, self._edit_index, self._framer())
            if not errors:
                registers[self._edit_index] = _clean(user_input)
                return self.async_create_entry(title="", data={CONF_REGISTERS: registers})

        return self.async_show_form(
            step_id="edit_register",
            data_schema=_register_schema(user_input or registers[self._edit_index]),
            errors=errors,
        )

    async def async_step_select_delete(self, user_input: dict[str, Any] | None = None):
        registers = self._registers()
        if not registers:
            return self.async_abort(reason="no_registers")

        if user_input is not None:
            index = int(user_input["register_index"])
            if 0 <= index < len(registers):
                registers.pop(index)
            return self.async_create_entry(title="", data={CONF_REGISTERS: registers})

        return self.async_show_form(step_id="select_delete", data_schema=_register_picker(registers))

    async def async_step_import_yaml(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            result = convert_yaml(user_input["yaml_text"])
            if result.yaml_error:
                return self.async_show_form(
                    step_id="import_yaml",
                    data_schema=_yaml_import_schema(user_input["yaml_text"]),
                    errors={"yaml_text": "yaml_invalid"},
                    description_placeholders={"yaml_error": result.yaml_error},
                )
            existing = self._registers()
            existing_ids = set()
            for reg in existing:
                try:
                    existing_ids.add(parse_register("x", reg).unique_id)
                except (KeyError, ValueError, TypeError):
                    continue
            new_regs = []
            for reg in result.registers:
                try:
                    uid = parse_register("x", reg).unique_id
                except (KeyError, ValueError, TypeError) as err:
                    result.skipped.append(Skipped(reg["name"], f"onverwachte fout: {err}"))
                    continue
                if uid in existing_ids:
                    result.skipped.append(Skipped(reg["name"], "een register met hetzelfde slave/adres/type bestaat al"))
                    continue
                existing_ids.add(uid)
                new_regs.append(reg)
            result.registers = new_regs
            self._import_result = result
            return await self.async_step_import_confirm()

        return self.async_show_form(step_id="import_yaml", data_schema=_yaml_import_schema(""))

    async def async_step_import_confirm(self, user_input: dict[str, Any] | None = None):
        result = self._import_result
        if result is None:
            return self.async_abort(reason="no_registers")

        if user_input is not None:
            if user_input.get("confirm"):
                if result.registers:
                    registers = self._registers()
                    registers.extend(result.registers)
                    self._import_result = None
                    return self.async_create_entry(title="", data={CONF_REGISTERS: registers})
                self._import_result = None
                return self.async_abort(reason="import_nothing_new")
            self._import_result = None
            return self.async_abort(reason="import_cancelled")

        lines = [f"Gevonden hubs: {', '.join(result.hubs_found) or '-'}", ""]
        if result.registers:
            lines.append(f"Worden geïmporteerd ({len(result.registers)}):")
            lines += [f"  • {r['name']}" for r in result.registers]
        else:
            lines.append("Geen registers om te importeren.")
        if result.notes:
            lines.append("")
            lines.append("Opmerkingen:")
            lines += [f"  • {n.name}: {n.reason}" for n in result.notes]
        if result.skipped:
            lines.append("")
            lines.append(f"Overgeslagen ({len(result.skipped)}):")
            lines += [f"  • {s.name}: {s.reason}" for s in result.skipped]

        return self.async_show_form(
            step_id="import_confirm",
            data_schema=vol.Schema({vol.Required("confirm", default=True): BooleanSelector()}),
            description_placeholders={"summary": "\n".join(lines)},
        )
