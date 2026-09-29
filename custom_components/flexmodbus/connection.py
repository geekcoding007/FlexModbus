from __future__ import annotations

from pymodbus import FramerType
from pymodbus.client import AsyncModbusTcpClient

from .const import CONNECT_TIMEOUT, FRAMER_RTU, FRAMER_SOCKET

_FRAMERS = {FRAMER_RTU: FramerType.RTU, FRAMER_SOCKET: FramerType.SOCKET}

def create_client(host: str, port: int, framer: str, retries: int = 2) -> AsyncModbusTcpClient:
    return AsyncModbusTcpClient(
        host,
        port=port,
        framer=_FRAMERS.get(framer, FramerType.RTU),
        timeout=CONNECT_TIMEOUT,
        retries=retries,
    )
