"""Omzetten van de YAML-configuratie van de ingebouwde Home Assistant Modbus-integratie
naar registers voor FlexModbus.

Bewust zonder Home Assistant-imports, zodat dit los te testen is.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from .const import DEVICE_CLASSES, STATE_CLASSES
from .register import parse_register

_DATA_TYPE_MAP = {
    "int16": "int16",
    "uint16": "uint16",
    "int32": "int32",
    "uint32": "uint32",
    "float32": "float32",
    "float": "float32",
}

_SWAP_MAP = {
    None: "abcd",
    "none": "abcd",
    "word": "cdab",
    "byte": "badc",
    "word_byte": "dcba",
}


@dataclass
class Skipped:
    name: str
    reason: str


@dataclass
class ImportResult:
    registers: list[dict] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)
    notes: list[Skipped] = field(default_factory=list)
    hubs_found: list[str] = field(default_factory=list)
    yaml_error: str | None = None


def _convert_sensor(hub_name: str, sensor: dict) -> tuple[dict | None, str | None]:
    name = str(sensor.get("name") or f"(naamloos register in {hub_name})")

    data_type_raw = sensor.get("data_type", "int16")
    data_type = _DATA_TYPE_MAP.get(data_type_raw)
    if data_type is None:
        return None, f"datatype '{data_type_raw}' wordt niet ondersteund (alleen int16/uint16/int32/uint32/float32/float)"

    swap = sensor.get("swap")
    if swap not in _SWAP_MAP:
        return None, f"swap-waarde '{swap}' wordt niet herkend"
    byte_order = _SWAP_MAP[swap]

    expected_count = 2 if data_type in ("int32", "uint32", "float32") else 1
    count = sensor.get("count", expected_count)
    if count != expected_count:
        return None, f"aantal registers ({count}) komt niet overeen met datatype {data_type_raw} (verwacht {expected_count})"

    try:
        address = int(sensor["address"]) + 1
    except (KeyError, ValueError, TypeError):
        return None, "geen geldig 'address' opgegeven"
    if address < 1:
        return None, "adres is ongeldig na omzetting (was negatief of ontbrak)"

    slave = sensor.get("device_address", sensor.get("slave", 1))
    try:
        slave = int(slave)
    except (ValueError, TypeError):
        return None, f"slave/device_address '{slave}' is geen geldig getal"

    register_type = sensor.get("input_type", "holding")
    if register_type not in ("holding", "input"):
        return None, f"input_type '{register_type}' wordt niet herkend"

    device_class = sensor.get("device_class") or "none"
    if device_class not in DEVICE_CLASSES:
        device_class = "none"

    state_class = sensor.get("state_class") or "none"
    if state_class not in STATE_CLASSES:
        state_class = "none"

    reg = {
        "name": name,
        "entity_type": "sensor",
        "entity_category": "none",
        "device_class": device_class,
        "state_class": state_class,
        "register_type": register_type,
        "address": address,
        "slave": slave,
        "data_type": data_type,
        "byte_order": byte_order,
        "unit_of_measurement": str(sensor.get("unit_of_measurement") or ""),
        "multiplier": float(sensor.get("scale", 1.0)) or 1.0,
        "offset": float(sensor.get("offset", 0.0)),
        "min_value": 0.0,
        "max_value": 100.0,
        "step_value": 1.0,
        "value_map": {},
        "bit_labels": {},
    }

    try:
        parse_register("preview", reg)
    except (KeyError, ValueError, TypeError) as err:
        return None, f"ongeldig na omzetting: {err}"

    precision = sensor.get("precision")
    note = None
    if precision is not None and precision != 3:
        note = f"let op: 'precision: {precision}' uit de YAML is niet overgenomen (FlexModbus rondt altijd af op 3 decimalen)"

    return reg, note


_UNSUPPORTED_PLATFORMS = {
    "binary_sensors": "binary_sensors (coils) worden niet ondersteund; FlexModbus werkt alleen met holding- en input-registers",
    "switches": "switches (coils) worden niet ondersteund; FlexModbus werkt alleen met holding- en input-registers",
    "covers": "covers worden niet ondersteund",
    "climates": "climate-entiteiten worden niet ondersteund",
}


def convert_yaml(text: str) -> ImportResult:
    """Zet de tekst van een Home Assistant modbus:-YAML-blok om naar FlexModbus-registers."""
    result = ImportResult()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        result.yaml_error = str(err)
        return result

    if data is None:
        result.yaml_error = "lege invoer"
        return result

    if isinstance(data, dict) and "modbus" in data:
        data = data["modbus"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        result.yaml_error = "onverwachte structuur: verwacht een 'modbus:'-lijst met hubs"
        return result

    for hub in data:
        if not isinstance(hub, dict):
            continue
        hub_name = str(hub.get("name") or "hub")
        result.hubs_found.append(hub_name)

        for platform, reason in _UNSUPPORTED_PLATFORMS.items():
            for entry in hub.get(platform, []) or []:
                entry_name = str(entry.get("name") or "?") if isinstance(entry, dict) else "?"
                result.skipped.append(Skipped(f"{entry_name} ({platform})", reason))

        for sensor in hub.get("sensors", []) or []:
            if not isinstance(sensor, dict):
                continue
            reg, error_or_note = _convert_sensor(hub_name, sensor)
            if reg is None:
                result.skipped.append(Skipped(str(sensor.get("name") or "?"), error_or_note or "onbekende fout"))
            else:
                result.registers.append(reg)
                if error_or_note:
                    result.notes.append(Skipped(reg["name"], error_or_note))

    return result
