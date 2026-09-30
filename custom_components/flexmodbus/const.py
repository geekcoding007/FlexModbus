from datetime import timedelta

DOMAIN = "flexmodbus"
MANUFACTURER = "FlexModbus"

CONF_REGISTERS = "registers"
CONF_REG_ADDRESS = "address"
CONF_REG_SLAVE = "slave"
CONF_REG_TYPE = "register_type"
CONF_DATA_TYPE = "data_type"
CONF_BYTE_ORDER = "byte_order"
CONF_MULTIPLIER = "multiplier"
CONF_OFFSET = "offset"
CONF_ENT_TYPE = "entity_type"
CONF_MIN = "min_value"
CONF_MAX = "max_value"
CONF_STEP = "step_value"
CONF_STATE_CLASS = "state_class"
CONF_FRAMER = "framer"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_REQUEST_DELAY = "request_delay_ms"
CONF_PERSISTENT_CONNECTION = "persistent_connection"
CONF_IDLE_CLOSE_SECONDS = "idle_close_seconds"
CONF_SUPPRESS_LOG_NOISE = "suppress_log_noise"
CONF_ENTITY_CATEGORY = "entity_category"
CONF_VALUE_MAP = "value_map"
CONF_BIT_LABELS = "bit_labels"
CONF_ON_VALUE = "on_value"
CONF_OFF_VALUE = "off_value"
CONF_STRING_LENGTH = "string_length"

ENTITY_SENSOR = "sensor"
ENTITY_NUMBER = "number"
ENTITY_SWITCH = "switch"
ENTITY_TYPES = [ENTITY_SENSOR, ENTITY_NUMBER, ENTITY_SWITCH]

REG_HOLDING = "holding"
REG_INPUT = "input"
REGISTER_TYPES = [REG_HOLDING, REG_INPUT]

FRAMER_SOCKET = "socket"
FRAMER_RTU = "rtu"
FRAMERS = [FRAMER_SOCKET, FRAMER_RTU]

DATA_TYPES = ["uint16", "int16", "uint32", "int32", "float32", "string"]
MIN_STRING_LENGTH = 1
MAX_STRING_LENGTH = 125

BYTE_ORDERS = ["abcd", "cdab", "badc", "dcba"]

LEGACY_BYTE_ORDERS = {
    "big_big": "abcd",
    "little_little": "cdab",
    "big_little": "badc",
    "little_big": "dcba",
}

DEVICE_CLASSES = [
    "none",
    "apparent_power",
    "battery",
    "current",
    "data_size",
    "duration",
    "energy",
    "energy_storage",
    "frequency",
    "gas",
    "humidity",
    "power",
    "power_factor",
    "pressure",
    "reactive_power",
    "temperature",
    "voltage",
    "water",
]
DEVICE_CLASSES_WITHOUT_UNIT = {"none", "power_factor"}

ENTITY_CATEGORIES = ["none", "diagnostic", "config"]

STATE_CLASSES = ["none", "measurement", "total_increasing"]

DEFAULT_SCAN_INTERVAL = 15
DEFAULT_REQUEST_DELAY = 350
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300
MIN_REQUEST_DELAY = 0
MAX_REQUEST_DELAY = 5000
DEFAULT_IDLE_CLOSE_SECONDS = 0
MIN_IDLE_CLOSE_SECONDS = 0
MAX_IDLE_CLOSE_SECONDS = 300

SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
OFFLINE_INTERVAL = timedelta(seconds=60)
MAX_TOLERATED_MISSES = 2
SILENCE_ABORT_AFTER = 3
REQUEST_DELAY = 0.35
CONNECT_TIMEOUT = 4.0
