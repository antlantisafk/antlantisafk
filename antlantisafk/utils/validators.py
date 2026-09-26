"""Input validators for server addresses, ports, and Minecraft versions.

These are pure functions with no I/O so they are trivially unit-testable.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Final

MAX_ADDRESS_LENGTH: Final[int] = 253  # DNS FQDN limit
MAX_LABEL_LENGTH: Final[int] = 63

# RFC 1123 hostname label: alnum, starts/ends alnum, may contain hyphens.
_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,%d}(?<!-)$" % MAX_LABEL_LENGTH
)

# Minecraft server addresses may legally contain underscores in some cases
# (many networks use e.g. play_myserver.net); we accept them deliberately.
_ALLOWED_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?!-)[A-Za-z0-9_-]{1,%d}(?<!-)$" % MAX_LABEL_LENGTH
)


class ValidationError(ValueError):
    """Raised when user input fails validation."""


def validate_nonempty(name: str, value: str, max_len: int = 4096) -> str:
    """Return ``value`` stripped, ensuring it is non-empty and bounded.

    Args:
        name: Field name used in the error message.
        value: Raw user input.
        max_len: Maximum accepted length.

    Raises:
        ValidationError: If the value is empty or too long.
    """
    stripped = (value or "").strip()
    if not stripped:
        raise ValidationError(f"{name} must not be empty.")
    if len(stripped) > max_len:
        raise ValidationError(f"{name} must be at most {max_len} characters.")
    return stripped


def validate_server_address(address: str) -> str:
    """Validate a Minecraft Java server address (hostname, FQDN, or IP).

    Accepts hostnames, IPv4, and IPv6 literals (IPv6 may be bracketed).
    Returns the normalised (stripped, brackets added for bare IPv6) address.

    Raises:
        ValidationError: If the address is malformed.
    """
    addr = (address or "").strip()
    if not addr:
        raise ValidationError("Server address must not be empty.")
    if len(addr) > MAX_ADDRESS_LENGTH + 2:
        raise ValidationError(f"Server address is too long (max {MAX_ADDRESS_LENGTH}).")

    # Bracketed IPv6 literal, e.g. [::1] or [2001:db8::1]
    if addr.startswith("[") and addr.endswith("]"):
        inner = addr[1:-1]
        try:
            ipaddress.IPv6Address(inner)
        except ValueError as exc:
            raise ValidationError(f"Invalid IPv6 address '{inner}'.") from exc
        return addr.lower()

    # Bare IP (v4 or v6)
    try:
        ipaddress.ip_address(addr)
        return addr.lower()
    except ValueError:
        pass

    # Hostname / FQDN: at least one label, each label RFC-1123-ish.
    labels = addr.rstrip(".").split(".")
    if len(labels) < 1 or any(
        not _ALLOWED_LABEL_RE.match(label) for label in labels
    ):
        raise ValidationError(
            f"'{address}' is not a valid server address. Use a hostname like "
            "play.example.net or an IP address."
        )
    if addr.endswith("."):
        raise ValidationError("Server address must not end with a dot.")
    return addr.lower()


def validate_port(port: int | str) -> int:
    """Validate a TCP port number, returning it as an ``int``.

    Accepts numeric strings for GUI round-trips.

    Raises:
        ValidationError: If the port is outside 1-65535 or not numeric.
    """
    try:
        p = int(str(port).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Port must be a number (got {port!r}).") from exc
    if not (1 <= p <= 65535):
        raise ValidationError(f"Port must be between 1 and 65535 (got {p}).")
    return p


def validate_minecraft_version(version: str) -> str:
    """Validate the Minecraft version field ('auto' or an X.Y[.Z] string).

    Returns the normalised lowercase value.

    Raises:
        ValidationError: If the version string is malformed.
    """
    v = (version or "").strip().lower()
    if v == "auto":
        return v
    if not re.match(r"^\d+\.\d+(\.\d+)?$", v):
        raise ValidationError(
            f"Minecraft version must be 'auto' or look like '1.20.4' (got {version!r})."
        )
    parts = [int(p) for p in v.split(".")]
    if parts[0] < 1 or (parts[0] == 1 and parts[1] > 99):
        raise ValidationError(f"Minecraft version '{v}' is out of the supported range.")
    return v
