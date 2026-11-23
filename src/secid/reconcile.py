"""Position reconciliation across sources that key securities differently.

A custodian file may key holdings by CUSIP, a fund administrator by ISIN and a
UK broker by SEDOL. ``reconcile`` resolves every identifier it can to a common
ISIN key (offline, using check-digit-validated conversion), then compares
quantities between the two sides.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from .identifiers import (
    CUSIP_COUNTRIES,
    SEDOL_COUNTRIES,
    IdType,
    cusip_to_isin,
    detect,
    normalize,
    sedol_to_isin,
)

__all__ = ["ReconRow", "canonical_key", "reconcile"]

MATCHED = "matched"
QUANTITY_BREAK = "quantity_break"
MISSING_LEFT = "missing_left"
MISSING_RIGHT = "missing_right"
INVALID = "invalid_identifier"


@dataclass(frozen=True)
class ReconRow:
    key: str
    status: str
    left_qty: Decimal | None
    right_qty: Decimal | None
    left_ids: tuple[str, ...] = ()
    right_ids: tuple[str, ...] = ()

    @property
    def difference(self) -> Decimal | None:
        if self.left_qty is None or self.right_qty is None:
            return None
        return self.left_qty - self.right_qty


def canonical_key(identifier: str, *, cusip_country: str = "US", sedol_country: str = "GB") -> str | None:
    """Return an ISIN for a CUSIP, SEDOL or ISIN, or None if it is invalid.

    CUSIPs are assumed to be ``cusip_country`` (US or CA) and SEDOLs
    ``sedol_country`` (GB or IE), since neither format encodes a country.
    """
    if cusip_country.upper() not in CUSIP_COUNTRIES or sedol_country.upper() not in SEDOL_COUNTRIES:
        raise ValueError("unsupported default country for CUSIP or SEDOL conversion")
    value = normalize(identifier)
    kind = detect(value)
    if kind is IdType.ISIN:
        return value
    if kind is IdType.CUSIP:
        return cusip_to_isin(value, cusip_country)
    if kind is IdType.SEDOL:
        return sedol_to_isin(value, sedol_country)
    return None


def _aggregate(
    positions: Iterable[tuple[str, Decimal | int | float | str]], **kwargs: str
) -> tuple[dict[str, Decimal], dict[str, list[str]], list[tuple[str, Decimal]]]:
    totals: dict[str, Decimal] = {}
    ids: dict[str, list[str]] = {}
    invalid: list[tuple[str, Decimal]] = []
    for identifier, qty in positions:
        amount = Decimal(str(qty))
        key = canonical_key(identifier, **kwargs)
        if key is None:
            invalid.append((normalize(identifier), amount))
            continue
        totals[key] = totals.get(key, Decimal(0)) + amount
        ids.setdefault(key, [])
        if normalize(identifier) not in ids[key]:
            ids[key].append(normalize(identifier))
    return totals, ids, invalid


def reconcile(
    left: Iterable[tuple[str, Decimal | int | float | str]] | Mapping[str, Decimal | int | float | str],
    right: Iterable[tuple[str, Decimal | int | float | str]] | Mapping[str, Decimal | int | float | str],
    *,
    tolerance: Decimal | float | str = 0,
    cusip_country: str = "US",
    sedol_country: str = "GB",
) -> list[ReconRow]:
    """Compare two position sets and return one row per security.

    Each side is an iterable of ``(identifier, quantity)`` pairs or a mapping.
    Duplicate rows for the same security (even under different identifier
    types) are summed. Rows whose absolute difference is within ``tolerance``
    count as matched. Results are sorted with breaks first, then by key.
    """
    if isinstance(left, Mapping):
        left = left.items()
    if isinstance(right, Mapping):
        right = right.items()
    kwargs = {"cusip_country": cusip_country, "sedol_country": sedol_country}
    l_totals, l_ids, l_invalid = _aggregate(left, **kwargs)
    r_totals, r_ids, r_invalid = _aggregate(right, **kwargs)
    tol = abs(Decimal(str(tolerance)))

    rows: list[ReconRow] = []
    for key in sorted(set(l_totals) | set(r_totals)):
        lq, rq = l_totals.get(key), r_totals.get(key)
        if lq is None:
            status = MISSING_LEFT
        elif rq is None:
            status = MISSING_RIGHT
        elif abs(lq - rq) <= tol:
            status = MATCHED
        else:
            status = QUANTITY_BREAK
        rows.append(ReconRow(key, status, lq, rq, tuple(l_ids.get(key, ())), tuple(r_ids.get(key, ()))))
    for raw, qty in l_invalid:
        rows.append(ReconRow(raw, INVALID, qty, None, (raw,), ()))
    for raw, qty in r_invalid:
        rows.append(ReconRow(raw, INVALID, None, qty, (), (raw,)))

    order = {INVALID: 0, QUANTITY_BREAK: 1, MISSING_LEFT: 2, MISSING_RIGHT: 2, MATCHED: 3}
    rows.sort(key=lambda r: (order[r.status], r.key))
    return rows
