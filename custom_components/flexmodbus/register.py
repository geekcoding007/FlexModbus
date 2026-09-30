from __future__ import annotations

import logging
import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    CONF_BYTE_ORDER,
    CONF_DATA_TYPE,
    CONF_ENT_TYPE,
    CONF_ENTITY_CATEGORY,
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
    CONF_VALUE_MAP,
    CONF_BIT_LABELS,
    CONF_ON_VALUE,
    CONF_OFF_VALUE,
    ENTITY_CATEGORIES,
    ENTITY_NUMBER,
    ENTITY_SENSOR,
    ENTITY_SWITCH,
    LEGACY_BYTE_ORDERS,
    REG_HOLDING,
    REGISTER_TYPES,
)

_LOGGER = logging.getLogger(__name__)

_FORMATS = {
    "uint16": ">H",
    "int16": ">h",
    "uint32": ">I",
    "int32": ">i",
    "float32": ">f",
}
_INT_RANGES = {
    "uint16": (0, 0xFFFF),
    "int16": (-0x8000, 0x7FFF),
    "uint32": (0, 0xFFFFFFFF),
    "int32": (-0x80000000, 0x7FFFFFFF),
}
_STRING_TYPES = {"string16": 16, "string32": 32}
_WORD_COUNT = {"uint16": 1, "int16": 1, "uint32": 2, "int32": 2, "float32": 2, **_STRING_TYPES}

_PERMUTATIONS = {
    "abcd": (0, 1, 2, 3),
    "cdab": (2, 3, 0, 1),
    "badc": (1, 0, 3, 2),
    "dcba": (3, 2, 1, 0),
}

def normalize_byte_order(value: str | None) -> str:
    value = LEGACY_BYTE_ORDERS.get(value, value)
    return value if value in _PERMUTATIONS else "abcd"

def is_string_type(data_type: str) -> bool:
    return data_type in _STRING_TYPES

def register_count(data_type: str) -> int:
    return _WORD_COUNT.get(data_type, 1)

def decode_registers(registers: list[int], data_type: str, byte_order: str) -> int | float | str:
    count = register_count(data_type)
    if len(registers) < count:
        raise ValueError(f"verwacht {count} registers, kreeg er {len(registers)}")

    if data_type in _STRING_TYPES:
        raw = b"".join(struct.pack(">H", int(r) & 0xFFFF) for r in registers[:count])
        return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()

    if count == 1:
        raw = struct.pack(">H", int(registers[0]) & 0xFFFF)
    else:
        wire = struct.pack(">HH", int(registers[0]) & 0xFFFF, int(registers[1]) & 0xFFFF)
        perm = _PERMUTATIONS[normalize_byte_order(byte_order)]
        raw = bytes(wire[i] for i in perm)
    return struct.unpack(_FORMATS[data_type], raw)[0]

def encode_value(raw: float, data_type: str, byte_order: str) -> list[int]:
    if data_type in _STRING_TYPES:
        raise ValueError("tekstregisters zijn alleen-lezen")
    if data_type == "float32":
        packed = struct.pack(">f", float(raw))
    else:
        number = int(math.floor(float(raw) + 0.5))
        low, high = _INT_RANGES[data_type]
        if not low <= number <= high:
            raise ValueError(f"waarde {number} valt buiten het bereik van {data_type} ({low}..{high})")
        packed = struct.pack(_FORMATS[data_type], number)

    if register_count(data_type) == 1:
        return [struct.unpack(">H", packed)[0]]

    perm = _PERMUTATIONS[normalize_byte_order(byte_order)]
    wire = bytes(packed[i] for i in perm)
    return list(struct.unpack(">HH", wire))

@dataclass(frozen=True)
class RegisterDef:
    unique_id: str
    name: str
    entity_type: str
    register_type: str
    address: int
    slave: int
    data_type: str
    byte_order: str
    unit: str | None
    multiplier: float
    offset: float
    device_class: str | None
    state_class: str | None
    entity_category: str | None
    value_map: dict[int, str] | None
    bit_labels: dict[int, str] | None
    on_value: int
    off_value: int
    min_value: float
    max_value: float
    step: float

    @property
    def protocol_address(self) -> int:
        return self.address - 1

    @property
    def count(self) -> int:
        return register_count(self.data_type)

    @property
    def is_enum(self) -> bool:
        return bool(self.value_map)

    @property
    def is_bitfield(self) -> bool:
        return bool(self.bit_labels)

    @property
    def is_switch(self) -> bool:
        return self.entity_type == ENTITY_SWITCH

    def to_value(self, raw: int | float | str) -> float | str | None:
        if isinstance(raw, str):
            return raw
        if self.value_map:
            code = int(raw)
            return self.value_map.get(code, f"Onbekend ({code})")
        if self.bit_labels:
            code = int(raw)
            width = 32 if self.data_type == "uint32" else 16
            active = [self.bit_labels[bit] for bit in sorted(self.bit_labels) if code & (1 << bit)]
            unlabeled = [
                f"bit{bit} (onbekend)" for bit in range(width) if (code & (1 << bit)) and bit not in self.bit_labels
            ]
            flags = active + unlabeled
            return ", ".join(flags) if flags else "Geen actieve vlaggen"
        if isinstance(raw, float) and not math.isfinite(raw):
            return None
        return round((raw * self.multiplier) + self.offset, 3)

    def to_raw(self, value: float) -> float:
        return (value - self.offset) / self.multiplier

def _none_if_empty(value: Any) -> str | None:
    if value in (None, "", "none"):
        return None
    return str(value)

def parse_register(entry_id: str, reg: Mapping[str, Any]) -> RegisterDef:
    entity_type = reg.get(CONF_ENT_TYPE, ENTITY_SENSOR)
    if entity_type not in (ENTITY_SENSOR, ENTITY_NUMBER, ENTITY_SWITCH):
        entity_type = ENTITY_SENSOR

    address = int(reg[CONF_REG_ADDRESS])
    if address < 1:
        raise ValueError("registeradres moet minimaal 1 zijn")
    slave = int(reg[CONF_REG_SLAVE])

    if entity_type in (ENTITY_NUMBER, ENTITY_SWITCH):
        register_type = REG_HOLDING
        prefix = "num" if entity_type == ENTITY_NUMBER else "switch"
        unique_id = f"modbus_{prefix}_{entry_id}_{slave}_{address}"
    else:
        register_type = reg.get(CONF_REG_TYPE, REG_HOLDING)
        if register_type not in REGISTER_TYPES:
            register_type = REG_HOLDING
        unique_id = f"modbus_{entry_id}_{slave}_{register_type}_{address}"

    data_type = reg.get(CONF_DATA_TYPE, "uint16")
    if data_type not in _FORMATS and data_type not in _STRING_TYPES:
        data_type = "uint16"
    is_text = data_type in _STRING_TYPES
    if is_text and entity_type in (ENTITY_NUMBER, ENTITY_SWITCH):
        raise ValueError("een tekstregister kan geen Number of Switch zijn")

    raw_value_map = reg.get(CONF_VALUE_MAP) or {}
    value_map: dict[int, str] | None = {int(k): str(v) for k, v in raw_value_map.items()} or None
    if value_map:
        if entity_type in (ENTITY_NUMBER, ENTITY_SWITCH):
            raise ValueError("een register met een waardenlijst kan geen Number of Switch zijn")
        if is_text or data_type == "float32":
            raise ValueError("een waardenlijst is niet mogelijk bij tekst of float32")

    raw_bit_labels = reg.get(CONF_BIT_LABELS) or {}
    bit_labels: dict[int, str] | None = {int(k): str(v) for k, v in raw_bit_labels.items()} or None
    if bit_labels:
        if entity_type in (ENTITY_NUMBER, ENTITY_SWITCH):
            raise ValueError("een register met bitvlaggen kan geen Number of Switch zijn")
        if data_type not in ("uint16", "uint32"):
            raise ValueError("bitvlaggen zijn alleen mogelijk bij uint16 of uint32")
        if value_map:
            raise ValueError("een waardenlijst en bitvlaggen kunnen niet samen op één register")
        width = 32 if data_type == "uint32" else 16
        if any(not (0 <= bit < width) for bit in bit_labels):
            raise ValueError(f"bitnummer moet tussen 0 en {width - 1} liggen voor {data_type}")

    on_value = int(reg.get(CONF_ON_VALUE, 1))
    off_value = int(reg.get(CONF_OFF_VALUE, 0))
    if entity_type == ENTITY_SWITCH:
        if is_text or data_type == "float32":
            raise ValueError("een Switch is niet mogelijk bij tekst of float32")
        if on_value == off_value:
            raise ValueError("de aan- en uit-waarde van een Switch moeten verschillend zijn")

    multiplier = float(reg.get(CONF_MULTIPLIER, 1.0)) or 1.0

    category = reg.get(CONF_ENTITY_CATEGORY, "none")
    if category not in ENTITY_CATEGORIES or category == "none":
        category = None
    elif category == "config" and entity_type == ENTITY_SENSOR:
        category = None

    return RegisterDef(
        unique_id=unique_id,
        name=str(reg["name"]),
        entity_type=entity_type,
        register_type=register_type,
        address=address,
        slave=slave,
        data_type=data_type,
        byte_order=normalize_byte_order(reg.get(CONF_BYTE_ORDER)),
        unit=None if is_text else (str(reg.get("unit_of_measurement") or "").strip() or None),
        multiplier=multiplier,
        offset=float(reg.get(CONF_OFFSET, 0.0)),
        device_class=None if is_text else _none_if_empty(reg.get("device_class")),
        state_class=None if is_text else _none_if_empty(reg.get(CONF_STATE_CLASS)),
        entity_category=category,
        value_map=value_map,
        bit_labels=bit_labels,
        on_value=on_value,
        off_value=off_value,
        min_value=float(reg.get(CONF_MIN, 0.0)),
        max_value=float(reg.get(CONF_MAX, 100.0)),
        step=float(reg.get(CONF_STEP, 1.0)) or 1.0,
    )

def get_raw_registers(entry: Any) -> list[dict[str, Any]]:
    if CONF_REGISTERS in entry.options:
        return [dict(r) for r in entry.options[CONF_REGISTERS]]
    return [dict(r) for r in entry.data.get(CONF_REGISTERS, [])]

def parse_registers(entry: Any) -> list[RegisterDef]:
    result: list[RegisterDef] = []
    seen: set[str] = set()
    for index, reg in enumerate(get_raw_registers(entry)):
        try:
            definition = parse_register(entry.entry_id, reg)
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.error("Register #%s in %s is ongeldig en wordt overgeslagen: %r", index + 1, entry.title, err)
            continue
        if definition.unique_id in seen:
            _LOGGER.warning("Register '%s' komt dubbel voor en wordt overgeslagen", definition.name)
            continue
        seen.add(definition.unique_id)
        result.append(definition)
    return result
