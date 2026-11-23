"""Validation and conversion for CUSIP, ISIN and SEDOL security identifiers.

All functions are pure and dependency-free so they can be used in batch
reconciliation jobs without network access.
"""

from __future__ import annotations

import re
from enum import Enum

__all__ = [
    "IdType",
    "InvalidIdentifier",
    "cusip_check_digit",
    "cusip_to_isin",
    "detect",
    "is_valid_cusip",
    "is_valid_isin",
    "is_valid_sedol",
    "isin_check_digit",
    "isin_to_cusip",
    "isin_to_sedol",
    "normalize",
    "sedol_check_digit",
    "sedol_to_isin",
]


class IdType(str, Enum):
    CUSIP = "CUSIP"
    ISIN = "ISIN"
    SEDOL = "SEDOL"


class InvalidIdentifier(ValueError):
    """Raised when an identifier fails format or check-digit validation."""


_CUSIP_RE = re.compile(r"^[0-9A-Z*@#]{8}[0-9]$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{9}[0-9]$")
# SEDOLs never contain vowels; the check digit is always numeric.
_SEDOL_RE = re.compile(r"^[0-9B-DF-HJ-NP-TV-Z]{6}[0-9]$")

# Countries whose ISIN national number is the CUSIP (CUSIP Global Services).
CUSIP_COUNTRIES = frozenset({"US", "CA"})
# Countries whose ISIN national number is "00" + SEDOL.
SEDOL_COUNTRIES = frozenset({"GB", "IE"})

_SEDOL_WEIGHTS = (1, 3, 1, 7, 3, 9)


def normalize(identifier: str) -> str:
    """Strip whitespace and upper-case an identifier."""
    if not isinstance(identifier, str):
        raise TypeError(f"identifier must be str, got {type(identifier).__name__}")
    return identifier.strip().upper()


def _char_value(ch: str) -> int:
    if ch.isdigit():
        return int(ch)
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    special = {"*": 36, "@": 37, "#": 38}
    if ch in special:
        return special[ch]
    raise InvalidIdentifier(f"invalid character {ch!r}")


def cusip_check_digit(base: str) -> str:
    """Return the check digit for the first 8 characters of a CUSIP."""
    base = normalize(base)
    if len(base) != 8 or not re.fullmatch(r"[0-9A-Z*@#]{8}", base):
        raise InvalidIdentifier(f"CUSIP base must be 8 characters: {base!r}")
    total = 0
    for i, ch in enumerate(base):
        v = _char_value(ch)
        if i % 2 == 1:
            v *= 2
        total += v // 10 + v % 10
    return str((10 - total % 10) % 10)


def isin_check_digit(base: str) -> str:
    """Return the Luhn check digit for the first 11 characters of an ISIN."""
    base = normalize(base)
    if not re.fullmatch(r"[A-Z]{2}[0-9A-Z]{9}", base):
        raise InvalidIdentifier(f"ISIN base must be 2 letters + 9 alphanumerics: {base!r}")
    digits = "".join(str(_char_value(ch)) for ch in base)
    total = 0
    # Double every second digit starting from the rightmost digit of the base,
    # because the check digit will be appended to its right.
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 0:
            n *= 2
        total += n // 10 + n % 10
    return str((10 - total % 10) % 10)


def sedol_check_digit(base: str) -> str:
    """Return the check digit for the first 6 characters of a SEDOL."""
    base = normalize(base)
    if not re.fullmatch(r"[0-9B-DF-HJ-NP-TV-Z]{6}", base):
        raise InvalidIdentifier(f"SEDOL base must be 6 characters without vowels: {base!r}")
    total = sum(_char_value(ch) * w for ch, w in zip(base, _SEDOL_WEIGHTS))
    return str((10 - total % 10) % 10)


def is_valid_cusip(value: str) -> bool:
    value = normalize(value)
    return bool(_CUSIP_RE.match(value)) and cusip_check_digit(value[:8]) == value[8]


def is_valid_isin(value: str) -> bool:
    value = normalize(value)
    return bool(_ISIN_RE.match(value)) and isin_check_digit(value[:11]) == value[11]


def is_valid_sedol(value: str) -> bool:
    value = normalize(value)
    return bool(_SEDOL_RE.match(value)) and sedol_check_digit(value[:6]) == value[6]


def detect(value: str) -> IdType | None:
    """Return the identifier type of a valid identifier, or None.

    Length makes the three formats unambiguous: SEDOL is 7, CUSIP 9, ISIN 12.
    """
    value = normalize(value)
    if len(value) == 12 and is_valid_isin(value):
        return IdType.ISIN
    if len(value) == 9 and is_valid_cusip(value):
        return IdType.CUSIP
    if len(value) == 7 and is_valid_sedol(value):
        return IdType.SEDOL
    return None


def cusip_to_isin(cusip: str, country: str = "US") -> str:
    """Build an ISIN from a CUSIP. Only US and CA ISINs embed a CUSIP."""
    cusip, country = normalize(cusip), normalize(country)
    if not is_valid_cusip(cusip):
        raise InvalidIdentifier(f"invalid CUSIP: {cusip!r}")
    if country not in CUSIP_COUNTRIES:
        raise InvalidIdentifier(f"CUSIP-based ISINs exist only for {sorted(CUSIP_COUNTRIES)}")
    base = country + cusip
    return base + isin_check_digit(base)


def sedol_to_isin(sedol: str, country: str = "GB") -> str:
    """Build an ISIN from a SEDOL. Only GB and IE ISINs embed a SEDOL."""
    sedol, country = normalize(sedol), normalize(country)
    if not is_valid_sedol(sedol):
        raise InvalidIdentifier(f"invalid SEDOL: {sedol!r}")
    if country not in SEDOL_COUNTRIES:
        raise InvalidIdentifier(f"SEDOL-based ISINs exist only for {sorted(SEDOL_COUNTRIES)}")
    base = country + "00" + sedol
    return base + isin_check_digit(base)


def isin_to_cusip(isin: str) -> str:
    """Extract the CUSIP from a US or CA ISIN."""
    isin = normalize(isin)
    if not is_valid_isin(isin):
        raise InvalidIdentifier(f"invalid ISIN: {isin!r}")
    if isin[:2] not in CUSIP_COUNTRIES:
        raise InvalidIdentifier(f"{isin} is not a US/CA ISIN, so it has no embedded CUSIP")
    return isin[2:11]


def isin_to_sedol(isin: str) -> str:
    """Extract the SEDOL from a GB or IE ISIN."""
    isin = normalize(isin)
    if not is_valid_isin(isin):
        raise InvalidIdentifier(f"invalid ISIN: {isin!r}")
    if isin[:2] not in SEDOL_COUNTRIES or isin[2:4] != "00":
        raise InvalidIdentifier(f"{isin} is not a GB/IE SEDOL-based ISIN")
    return isin[4:11]
