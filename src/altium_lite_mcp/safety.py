"""Input validation and output sanitising.

Text from design files is untrusted: it is returned only inside data fields
and clipped to a fixed length.
"""

from __future__ import annotations

import math
import re

from .config import Config
from .models import E_INVALID_INPUT, E_MODE_READ_ONLY, AltiumError

MAX_VALUE_LEN = 255
MAX_LIST_LIMIT = 500
DEFAULT_LIST_LIMIT = 200
MAX_GET_DESIGNATORS = 25
MAX_CHANGES = 50          # per tool call for the plain edit tools
MAX_BULK_CHANGES = 500    # table import / project-wide rename or delete
BRIDGE_CHUNK = 50         # changes sent to the script per request
MAX_QUERY_LEN = 100
MAX_CSV_BYTES = 100_000
MAX_MIL = 100_000.0       # |coordinate| limit for moves (100 inch)

_DESIGNATOR_RE = re.compile(r"^[A-Za-z0-9_.\-\[\]]{1,32}$")
_PARAM_NAME_RE = re.compile(r"^[A-Za-z0-9_ .\-]{1,64}$")
_FIELD_RE = re.compile(r"^(any|designator|comment|library_ref|footprint|sheet|parameter:[A-Za-z0-9_ .\-]{1,64})$")
_GROUP_FIELD_RE = re.compile(r"^(comment|library_ref|footprint|sheet|parameter:[A-Za-z0-9_ .\-]{1,64})$")

# Names the MVP will not write (matched case-insensitively, spaces removed).
RESERVED_PARAMETERS = frozenset(
    {"designator", "libreference", "libref", "footprint", "pcbfootprint", "model", "models", "comment"}
)


def require_writable(config: Config) -> None:
    if not config.writable:
        raise AltiumError(E_MODE_READ_ONLY, "The server is in read-only mode; writes are disabled.")


def require_save(config: Config) -> None:
    if not config.can_save:
        raise AltiumError(
            E_MODE_READ_ONLY,
            "Saving is disabled. Set ALTIUM_LITE_MODE=read_write_save in the server's environment and restart it.",
        )


def check_designator(value: str) -> str:
    if not isinstance(value, str) or not _DESIGNATOR_RE.match(value):
        raise AltiumError(E_INVALID_INPUT, f"Invalid designator {clip(str(value), 40)!r}.")
    return value


def check_parameter_name(value: str) -> str:
    if not isinstance(value, str) or not _PARAM_NAME_RE.match(value) or value != value.strip():
        raise AltiumError(E_INVALID_INPUT, f"Invalid parameter name {clip(str(value), 40)!r}.")
    return value


def check_value(value: str) -> str:
    if not isinstance(value, str):
        raise AltiumError(E_INVALID_INPUT, "Parameter value must be a string.")
    if len(value) > MAX_VALUE_LEN:
        raise AltiumError(E_INVALID_INPUT, f"Parameter value is longer than {MAX_VALUE_LEN} characters.")
    for ch in value:
        o = ord(ch)
        if o < 32 or o == 127:
            raise AltiumError(E_INVALID_INPUT, "Parameter value contains control characters.")
        if o > 0xFF:
            raise AltiumError(
                E_INVALID_INPUT,
                "Parameter value contains characters above U+00FF, which DelphiScript cannot round-trip.",
            )
    return value


def check_limit_offset(limit: int, offset: int) -> None:
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise AltiumError(E_INVALID_INPUT, f"limit must be between 1 and {MAX_LIST_LIMIT}.")
    if offset < 0:
        raise AltiumError(E_INVALID_INPUT, "offset must be 0 or greater.")


def check_query(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_QUERY_LEN:
        raise AltiumError(E_INVALID_INPUT, f"query must be 1 to {MAX_QUERY_LEN} characters.")
    return value


def check_field(value: str) -> str:
    if not _FIELD_RE.match(value):
        raise AltiumError(
            E_INVALID_INPUT,
            "field must be any, designator, comment, library_ref, footprint, sheet or parameter:<Name>.",
        )
    return value


def check_group_field(value: str) -> str:
    if not _GROUP_FIELD_RE.match(value):
        raise AltiumError(
            E_INVALID_INPUT,
            "group_by entries must be comment, library_ref, footprint, sheet or parameter:<Name>.",
        )
    return value


def check_mil(value: float, what: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or abs(value) > MAX_MIL:
        raise AltiumError(E_INVALID_INPUT, f"{what} must be a finite number within +/-{MAX_MIL:g} mil.")
    return float(value)


def is_reserved(name: str) -> bool:
    return name.replace(" ", "").lower() in RESERVED_PARAMETERS


def clip(value: str, length: int = MAX_VALUE_LEN) -> str:
    return value if len(value) <= length else value[: length - 1] + "…"
