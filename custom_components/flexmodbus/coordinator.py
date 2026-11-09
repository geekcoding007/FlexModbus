from __future__ import annotations

import asyncio
import inspect
import logging
import struct
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException, ModbusIOException

from .const import (
    CONF_IDLE_CLOSE_SECONDS,
    CONF_PERSISTENT_CONNECTION,
    CONF_REQUEST_DELAY,
    CONF_SCAN_INTERVAL,
    CONF_SUNSPEC_DEVICE,
    DEFAULT_IDLE_CLOSE_SECONDS,
    DEFAULT_REQUEST_DELAY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_COMBINED_READ_SPAN,
    MAX_TOLERATED_MISSES,
    REG_INPUT,
    SILENCE_ABORT_AFTER,
    SUNSPEC_SF_MAX,
    SUNSPEC_SF_MIN,
)
from .register import RegisterDef, decode_registers, encode_value, is_nan_raw

_LOGGER = logging.getLogger(__name__)

_COMM_ERRORS = (ModbusException, OSError, TimeoutError)

def _unit_kwarg(client: AsyncModbusTcpClient) -> str:
    params = inspect.signature(client.read_holding_registers).parameters
    return "device_id" if "device_id" in params else "slave"

def _is_foreign(result, reg: RegisterDef, count: int | None = None) -> bool:
    expected = reg.count if count is None else count
    dev = getattr(result, "dev_id", None)
    if dev is None:
        dev = getattr(result, "slave_id", None)
    if dev not in (None, 0) and reg.slave not in (0, 255) and dev != reg.slave:
        return True
    if not result.isError() and len(result.registers) != expected:
        return True
    return False

class ModbusCoordinator(DataUpdateCoordinator[dict[str, float | str | None]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AsyncModbusTcpClient,
        registers: list[RegisterDef],
    ) -> None:
        self._scan_interval = timedelta(
            seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._request_delay = entry.data.get(CONF_REQUEST_DELAY, DEFAULT_REQUEST_DELAY) / 1000
        if CONF_IDLE_CLOSE_SECONDS in entry.data:
            self._idle_close = entry.data[CONF_IDLE_CLOSE_SECONDS]
        elif entry.data.get(CONF_PERSISTENT_CONNECTION, True) is False:
            self._idle_close = 5
        else:
            self._idle_close = DEFAULT_IDLE_CLOSE_SECONDS
        self._idle_close_handle = None
        self._offline_interval = max(self._scan_interval * 4, timedelta(seconds=60))

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            config_entry=entry,
            update_interval=self._scan_interval,
        )
        self.client = client
        self.registers = registers
        self._host = entry.data[CONF_HOST]
        self._lock = asyncio.Lock()
        self._unit_kw = _unit_kwarg(client)
        self._failing: set[str] = set()
        self._misses: dict[str, int] = {}
        self._ever_ok: set[str] = set()
        self._decode_errors = 0
        self._sunspec = bool(entry.data.get(CONF_SUNSPEC_DEVICE, False))
        self._rejecting: set[str] = set()

    def _cancel_idle_close(self) -> None:
        if self._idle_close_handle is not None:
            self._idle_close_handle.cancel()
            self._idle_close_handle = None

    def _schedule_idle_close(self) -> None:
        self._cancel_idle_close()
        if self._idle_close > 0:
            self._idle_close_handle = self.hass.loop.call_later(self._idle_close, self.client.close)

    def async_shutdown_idle_timer(self) -> None:
        self._cancel_idle_close()

    async def _ensure_connected(self) -> None:
        self._cancel_idle_close()
        if self.client.connected:
            return
        self.client.close()
        try:
            await self.client.connect()
        except _COMM_ERRORS as err:
            raise ConnectionError(f"Geen verbinding met {self._host}: {err}") from err
        if not self.client.connected:
            raise ConnectionError(f"Geen verbinding met {self._host}")

    async def _read(self, reg: RegisterDef, start: int | None = None, count: int | None = None):
        start = reg.protocol_address if start is None else start
        count = reg.count if count is None else count
        kwargs = {self._unit_kw: reg.slave}
        if reg.register_type == REG_INPUT:
            return await self.client.read_input_registers(start, count=count, **kwargs)
        return await self.client.read_holding_registers(start, count=count, **kwargs)

    @staticmethod
    def _combined_plan(reg: RegisterDef) -> tuple[int, int, int, int] | None:
        """Waarde en schaalfactor in een verzoek lezen, zodat ze altijd bij elkaar horen.

        Geeft (start, aantal, offset waarde, offset schaalfactor), of None als er geen
        schaalfactor is of de registers te ver uit elkaar liggen."""
        if not reg.has_scale_factor:
            return None
        sf = reg.scale_factor_address - 1
        low = min(reg.protocol_address, sf)
        high = max(reg.protocol_address + reg.count, sf + 1)
        if high - low > MAX_COMBINED_READ_SPAN:
            return None
        return low, high - low, reg.protocol_address - low, sf - low

    def _mark_failed(self, reg: RegisterDef, reason: str) -> None:
        if reg.unique_id not in self._failing:
            self._failing.add(reg.unique_id)
            _LOGGER.warning(
                "Register '%s' (slave %s, adres %s) kon niet worden gelezen: %s",
                reg.name, reg.slave, reg.address, reason,
            )

    def _mark_ok(self, reg: RegisterDef) -> None:
        self._misses.pop(reg.unique_id, None)
        self._rejecting.discard(reg.unique_id)
        self._ever_ok.add(reg.unique_id)
        if reg.unique_id in self._failing:
            self._failing.discard(reg.unique_id)
            _LOGGER.info("Register '%s' geeft weer antwoord", reg.name)

    def _fail(self, reg: RegisterDef, reason: str) -> float | str | None:
        misses = self._misses.get(reg.unique_id, 0) + 1
        self._misses[reg.unique_id] = misses
        previous = (self.data or {}).get(reg.unique_id) if self.last_update_success else None
        if previous is not None and misses <= MAX_TOLERATED_MISSES:
            _LOGGER.debug(
                "Register '%s' gaf geen bruikbaar antwoord (%s), laatste waarde blijft staan (%s/%s)",
                reg.name, reason, misses, MAX_TOLERATED_MISSES,
            )
            return previous
        self._mark_failed(reg, reason)
        return None

    def _reject(self, reg: RegisterDef, reason: str, quiet: bool = False) -> float | str | None:
        """Ongeldige inhoud (sentinel, onmogelijke waarde): de laatste goede waarde blijft staan."""
        previous = (self.data or {}).get(reg.unique_id) if self.last_update_success else None
        if reg.unique_id not in self._rejecting:
            self._rejecting.add(reg.unique_id)
            _LOGGER.log(
                logging.DEBUG if quiet else logging.WARNING,
                "Register '%s' (slave %s, adres %s): ongeldige waarde genegeerd: %s",
                reg.name, reg.slave, reg.address, reason,
            )
        if previous is not None:
            return previous
        if not quiet:
            self._mark_failed(reg, reason)
        return None

    def _zero(self, reg: RegisterDef) -> float:
        self._decode_errors = 0
        self._mark_ok(reg)
        return 0.0

    async def _request(
        self, reg: RegisterDef, start: int, count: int, answered: bool, label: str = ""
    ) -> tuple[object | None, tuple[float | str | None, bool] | None]:
        """Een leesverzoek; geeft (antwoord, None) of (None, (waarde, answered)) als het mislukt."""
        for _ in range(2):
            try:
                result = await self._read(reg, start, count)
            except _COMM_ERRORS as err:
                if not self.client.connected:
                    raise ConnectionError("Verbinding verbroken tijdens uitlezen") from err
                if isinstance(err, ModbusIOException):
                    self._decode_errors += 1
                    if self._decode_errors >= 3:
                        self._decode_errors = 0
                        self.client.close()
                        raise ConnectionError(
                            "Herhaaldelijk onleesbare Modbus-frames ontvangen; verbinding wordt opnieuw opgebouwd"
                        ) from err
                return None, (self._fail(reg, f"{label}{err!r}"), answered)
            if not _is_foreign(result, reg, count):
                return result, None
            _LOGGER.debug(
                "Register '%s': antwoord genegeerd dat niet bij het verzoek past "
                "(slave %s, %s registers; gevraagd: slave %s, %s registers)",
                reg.name, getattr(result, "dev_id", getattr(result, "slave_id", "?")),
                len(getattr(result, "registers", []) or []), reg.slave, count,
            )
        return None, (
            self._fail(
                reg,
                f"{label}alleen antwoorden ontvangen die niet bij het verzoek passen "
                "(ander slave-ID of ander aantal registers)",
            ),
            answered,
        )

    async def _read_value(self, reg: RegisterDef) -> tuple[float | str | None, bool]:
        plan = self._combined_plan(reg)
        start, count, value_offset, sf_offset = plan or (reg.protocol_address, reg.count, 0, None)

        result, failure = await self._request(reg, start, count, answered=False)
        if failure is not None:
            return failure
        if result.isError():
            return self._fail(reg, str(result)), True

        try:
            raw = decode_registers(
                result.registers[value_offset:value_offset + reg.count],
                reg.data_type, reg.byte_order, reg.string_length,
            )
        except (ValueError, struct.error) as err:
            return self._fail(reg, f"ongeldige data: {err}"), True

        checks_sentinel = reg.has_scale_factor or (self._sunspec and reg.is_plain_numeric_sensor)
        if checks_sentinel and is_nan_raw(reg.data_type, raw):
            if reg.nan_as_zero:
                return self._zero(reg), True
            return self._reject(reg, "waarde is niet beschikbaar (SunSpec NaN-sentinel)", quiet=True), True

        scale_factor = None
        if reg.has_scale_factor:
            if sf_offset is not None:
                sf_registers = result.registers[sf_offset:sf_offset + 1]
            else:
                sf_result, failure = await self._request(
                    reg, reg.scale_factor_address - 1, 1, answered=True, label="schaalfactor-register: "
                )
                if failure is not None:
                    return failure
                if sf_result.isError():
                    return self._fail(reg, f"schaalfactor-register gaf een foutmelding: {sf_result}"), True
                sf_registers = sf_result.registers
            try:
                scale_factor = decode_registers(sf_registers, "int16", "abcd")
            except (ValueError, struct.error) as err:
                return self._fail(reg, f"ongeldige schaalfactor-data: {err}"), True
            if is_nan_raw("int16", scale_factor):
                if reg.nan_as_zero:
                    return self._zero(reg), True
                return self._reject(reg, "schaalfactor is niet beschikbaar (SunSpec NaN-sentinel)", quiet=True), True
            if not SUNSPEC_SF_MIN <= scale_factor <= SUNSPEC_SF_MAX:
                return self._reject(
                    reg, f"schaalfactor {scale_factor} valt buiten het SunSpec-bereik {SUNSPEC_SF_MIN}..{SUNSPEC_SF_MAX}"
                ), True

        value = reg.to_value(raw, scale_factor=scale_factor)
        if value is None:
            return self._reject(reg, "waarde is geen geldig getal (NaN/oneindig)"), True
        if not reg.is_plausible(value):
            return self._reject(
                reg, f"onmogelijke waarde {value} (toegestaan: {reg.valid_min}..{reg.valid_max})"
            ), True

        self._decode_errors = 0
        self._mark_ok(reg)
        return value, True

    async def _poll(self) -> dict[str, float | str | None]:
        data: dict[str, float | str | None] = {}
        failed = 0
        silent_streak = 0

        async with self._lock:
            try:
                await self._ensure_connected()
                for reg in self.registers:
                    value, answered = await self._read_value(reg)
                    data[reg.unique_id] = value
                    if value is None:
                        failed += 1

                    if answered:
                        silent_streak = 0
                    elif reg.unique_id in self._ever_ok or not self._ever_ok:
                        silent_streak += 1
                        if silent_streak >= SILENCE_ABORT_AFTER:
                            raise ConnectionError(
                                f"Het apparaat antwoordt niet ({SILENCE_ABORT_AFTER} registers achter elkaar "
                                "zonder antwoord). Staat het uit, is de bus verstoord, of zijn de eerste registers onjuist ingesteld?"
                            )
                    await asyncio.sleep(self._request_delay)
            except ConnectionError as err:
                raise UpdateFailed(str(err)) from err
            finally:
                self._schedule_idle_close()

        if self.registers and failed == len(self.registers):
            raise UpdateFailed(
                "Geen enkel register gaf een geldig antwoord. Controleer het verbindingstype "
                "(Modbus TCP of RTU over TCP), het slave-ID en de registeradressen."
            )
        return data

    async def _async_update_data(self) -> dict[str, float | str | None]:
        try:
            data = await self._poll()
        except UpdateFailed:
            self.update_interval = self._offline_interval
            raise
        self.update_interval = self._scan_interval
        return data

    async def async_write(self, reg: RegisterDef, value: float) -> None:
        try:
            payload = encode_value(reg.to_raw(value), reg.data_type, reg.byte_order)
        except (ValueError, struct.error) as err:
            raise HomeAssistantError(f"Kan {value} niet omzetten voor '{reg.name}': {err}") from err

        kwargs = {self._unit_kw: reg.slave}
        async with self._lock:
            try:
                await self._ensure_connected()
                if len(payload) == 1:
                    result = await self.client.write_register(reg.protocol_address, payload[0], **kwargs)
                else:
                    result = await self.client.write_registers(reg.protocol_address, payload, **kwargs)
            except _COMM_ERRORS as err:
                raise HomeAssistantError(f"Schrijven naar '{reg.name}' mislukt: {err}") from err
            finally:
                await asyncio.sleep(self._request_delay)
                self._schedule_idle_close()

        if result.isError():
            raise HomeAssistantError(f"Apparaat weigerde schrijven naar '{reg.name}': {result}")

ModbusConfigEntry = ConfigEntry[ModbusCoordinator]
