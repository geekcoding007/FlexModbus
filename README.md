# FlexModbus

*[Lees dit in het Nederlands](README.nl.md)*

Freely configurable Modbus TCP integration for Home Assistant. No fixed register list per device, unlike most ready-made Modbus integrations — you define which registers to read (as a sensor) or set (as a number), with the data type, byte order, unit and scaling that match your device.

Built and extended while connecting a SolarEdge and a Solplanet inverter through Waveshare RS485-to-Ethernet gateways, but not tied to those devices: everything is configurable.

## Features

- **Fully self-configured registers** — no fixed device profiles. Holding and input registers, with address, slave ID, data type and byte order.
- **Data types**: `uint16`, `int16`, `uint32`, `int32`, `float32`, and text (`string16` / `string32`, SunSpec notation: the number is the register count, so max. 32 and 64 characters respectively).
- **Byte order**: ABCD (big endian), CDAB, BADC, DCBA (little endian) — for 32-bit values.
- **Sensor and Number entities**: read-only values or writable setpoints (Number is limited to holding registers).
- **Entity category**: normal, diagnostic, or config (the latter only for Number).
- **Value list for status codes**: map a raw code (e.g. `0`, `1`, `2`) to readable text (`Wait`, `Normal`, `Fault`), rendered as a proper Home Assistant enum sensor with a dropdown of possible states. Sensor only; not for text or float32 registers.
- **Bit flags for status/error registers (B16/B32)**: show which individual bits in a register are active as readable, comma-separated text (e.g. "Communication error, Cell voltage too high"). Sensor only, `uint16`/`uint32`, cannot be combined with a value list on the same register.
- **Import from YAML**: convert sensors from Home Assistant's built-in Modbus integration (a `modbus:` block in `configuration.yaml`) into FlexModbus registers in one go, with a preview of what can and can't be carried over before anything is saved.
- **Two connection types**: plain Modbus TCP, or RTU framing over TCP for transparent serial gateways.
- **One shared connection per device**: all registers are read in a single round over one connection, instead of every entity polling independently.
- **Configurable per device**: poll interval, delay between requests, and how long the connection stays open after inactivity before closing itself.
- **Robust error handling**: a single missed response holds the last value (instead of immediately going "unavailable"); an entity only becomes unavailable after a few failures in a row. Responses with the wrong slave ID or the wrong register count (e.g. from other traffic on the same bus) are detected and ignored.
- **Optional**: filter known, harmless pymodbus error messages (caused by a device sending unsolicited traffic on the line) out of the Home Assistant log.
- Dutch and English translations.

## Requirements

- Home Assistant 2024.8 or newer (uses `ConfigEntry.runtime_data` and the reconfigure flow; older versions are untested).
- `pymodbus` 3.8 or newer. The newer `device_id` parameter needs 3.10+; on older versions the integration automatically falls back to the older `slave` parameter.

## Installation

### Via HACS (recommended)

1. HACS → **Integrations** → menu (⋮) top right → **Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Search for "FlexModbus" and install.
4. Restart Home Assistant.

### Manual

1. Copy the `custom_components/flexmodbus` folder into your Home Assistant configuration's `custom_components` folder.
2. Restart Home Assistant.

## Adding your first device

**Settings → Devices & services → Add integration → FlexModbus.**

| Field | Explanation |
|---|---|
| Name | Free-form name for this device, e.g. "Inverter". |
| IP address (host) | Address of the device or the RS485-to-Ethernet gateway. |
| Port | Usually 502. |
| Connection type | **Modbus TCP**: the standard protocol, for devices with their own network port or a gateway set to "Modbus TCP to RTU" mode. **RTU over TCP**: only for a gateway that passes data through transparently (protocol "None"/"Transparent"), where raw RTU frames travel over the bare TCP connection. |
| Poll interval | How often all registers are read in one round (5-300 s, default 15 s). Increase for a slow or unstable device. |
| Delay between requests | Wait time on the bus between two requests (0-5000 ms, default 350 ms). Increase if a busy device gets confused by polling too fast. |
| Close connection after inactivity | 0 = never close automatically (default, fastest). Above 0: the connection closes after that many seconds of inactivity and reopens on the next action — a middle ground between always open (more exposed to unsolicited traffic from the device) and closing immediately after every round (more overhead, can noticeably slow polling with a slow gateway). |
| Hide known pymodbus noise from the log | Hides specific, known, harmless messages (see Troubleshooting below). Applies Home Assistant-wide as long as at least one device has this enabled. |

The connection is tested when you save; if it fails, the form stays open with an error.

## Managing registers

Go to the integration → **Configure** (the gear icon) to add, edit or delete registers.

| Field | Explanation |
|---|---|
| Name | Name of the entity. |
| Entity type | Sensor (read-only) or Number (writable, holding registers only). |
| Category | Normal, Diagnostic, or Configuration (Number only). |
| Device class | Determines the icon and unit convention in Home Assistant (power, energy, temperature, ...). |
| State class | For sensors: "Measurement" (fluctuates) or "Total increasing" (only counts up, for energy meters). |
| Register type | Holding or Input. A Number can only be Holding. |
| Register number | As in the device's manual — 1 is the first register (1-based, not 0-based). |
| Slave/unit ID | The device's Modbus address on the bus (often 1). |
| Data type | See Features above. For a text type (`string16`/`string32`), byte order, multiplier, offset, unit and classes are automatically dropped. |
| Byte order | Only relevant for 32-bit values (2 registers). See Troubleshooting below if a value is completely off. |
| Unit | E.g. `W`, `kWh`, `°C`. Required once a device class that needs a unit is selected. |
| Multiplier / offset | Value = raw register value × multiplier + offset. |
| Minimum / maximum / step | Number only. |
| Value list (optional) | One line per code, formatted as `code: label`, e.g.:<br>`0: Wait`<br>`1: Normal`<br>`2: Fault`<br>`4: Checking`<br>Leave empty for a plain number. Sensor only, not for text or float32 registers. A code not in the list is shown as "Unknown (code)". |
| Bit flags (optional) | For B16/B32 registers (individual on/off flags in one number, such as error status registers). One line per bit, formatted as `bit number: label`, e.g.:<br>`0: Communication error`<br>`1: Cell voltage too high`<br>`3: Temperature too high`<br>Shows all active bits, comma-separated ("No active flags" if none are set); an unlabeled active bit appears as "bitN (unknown)". Sensor only, data type `uint16` (bit 0-15) or `uint32` (bit 0-31), and cannot be combined with a value list on the same register. |

Changes to registers automatically reload the integration.

## Changing the connection

Integration → **⋮ → Reconfigure** to change the host, port, connection type, poll interval, delay or log filter later. Your registers are kept.

## Importing from Home Assistant's built-in Modbus integration

Already have a `modbus:` block in your `configuration.yaml`? You can import the sensors from it instead of entering them all by hand again.

Integration → **Configure → Import from YAML**. Paste the `modbus:` block (or just the relevant hub) and you'll first see a preview — what will be imported, what will be skipped and why — before anything is saved.

**What gets converted:**
- Sensors with data type `int16`, `uint16`, `int32`, `uint32`, `float32` or `float` (defaults to `int16` if unspecified, matching the original YAML).
- `swap: word` → byte order CDAB, `swap: byte` → BADC, `swap: word_byte` → DCBA, no `swap` → ABCD.
- `scale` → multiplier, `offset` → offset, `slave`/`device_address` → slave ID. The address is automatically increased by 1 (Home Assistant counts from 0, FlexModbus from 1).
- Registers that already exist (same slave/address/type) are detected and not added twice.

**What gets skipped** (with the reason shown in the preview):
- 64-bit types (`int64`, `uint64`, `float64`), `string`/`custom` registers with a variable register count.
- `binary_sensors`, `switches`, `covers` and `climates` — these are based on coils, and FlexModbus only works with holding and input registers.
- A `count` that doesn't match the data type.
- `precision` is not carried over (FlexModbus always rounds to 3 decimals); the register is still imported, with a note in the preview.

This import feature doesn't change your existing `configuration.yaml` — you can remove that yourself once you've fully switched to FlexModbus.

## Troubleshooting

**All registers return "no response".**
Check, in this order: the connection type (Modbus TCP vs. RTU over TCP — this is the most common cause), the slave ID, and whether the register addresses are correct (1-based).

**One specific 32-bit value is completely wrong, others aren't.**
Almost always the wrong byte order. Try the other three options.

**"request ask for id=X but got id=Y" / "Unable to decode frame" / "Fatal error: protocol.data_received() call failed" in the log.**
This means something other than our own requests is appearing on the same line — for example an inverter searching internally for a meter that isn't connected, or a gateway with multiple simultaneous clients (multi-host) enabled. The integration already detects and ignores these stray responses itself; your sensors keep updating normally. If you don't want to see this in the log, enable **"Hide known pymodbus noise from the log"** on the device. If the message appears very frequently (every few seconds), look for the source: a setting on the device itself that searches for a non-existent meter, or a gateway setting such as "multi-host".

**Measurements become slower after setting "close connection after inactivity".**
At a low value (e.g. 0-5 s), the connection is rebuilt on almost every poll round. Some gateways are slow at this. Set the value higher than your poll interval to effectively keep the connection open continuously, with just a safety net for longer periods of silence.

**pymodbus version older than 3.10.**
The integration detects this automatically and uses the older `slave=` parameter instead of `device_id=`. No action needed.

## Contributing

Issues and pull requests are welcome via this repository's issue tracker.

## License

MIT — see [LICENSE](LICENSE).
