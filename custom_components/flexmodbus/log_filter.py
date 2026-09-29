from __future__ import annotations

import logging

_PYMODBUS_LOGGER = "pymodbus.logging"
_HA_LOGGER = "homeassistant"

_NOISE_PATTERNS = (
    "request ask for id=",
    "Unable to decode frame",
    "received pdu without a corresponding request",
    "No response received after",
    "Repeating....",
)

class PymodbusNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.WARNING:
            return True
        message = record.getMessage()
        return not any(pattern in message for pattern in _NOISE_PATTERNS)

class PymodbusFatalFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.ERROR:
            return True
        if "protocol.data_received() call failed" not in record.getMessage():
            return True
        exc_info = record.exc_info
        exc = exc_info[1] if isinstance(exc_info, tuple) and len(exc_info) > 1 else None
        if exc is not None and type(exc).__module__.startswith("pymodbus"):
            return False
        return True

_noise_filter = PymodbusNoiseFilter()
_fatal_filter = PymodbusFatalFilter()
_enabled_by: set[str] = set()

def enable(owner_id: str) -> None:
    _enabled_by.add(owner_id)
    logging.getLogger(_PYMODBUS_LOGGER).addFilter(_noise_filter)
    logging.getLogger(_HA_LOGGER).addFilter(_fatal_filter)

def disable(owner_id: str) -> None:
    _enabled_by.discard(owner_id)
    if not _enabled_by:
        logging.getLogger(_PYMODBUS_LOGGER).removeFilter(_noise_filter)
        logging.getLogger(_HA_LOGGER).removeFilter(_fatal_filter)
