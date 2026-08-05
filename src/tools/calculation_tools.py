from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


TWOPLACES = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def money_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def sum_money(values: list[Any]) -> float:
    total = sum((Decimal(str(v)) for v in values), Decimal("0"))
    return float(money(total))


def add_money(a: Any, b: Any) -> float:
    return float(money(Decimal(str(a)) + Decimal(str(b))))


def subtract_money(a: Any, b: Any) -> float:
    return float(money(Decimal(str(a)) - Decimal(str(b))))


def compare_money_with_tolerance(a: Any, b: Any, tolerance: Any = "0.10") -> bool:
    return abs(Decimal(str(a)) - Decimal(str(b))) <= Decimal(str(tolerance))


def hours_between(timestamp_a: str | None, timestamp_b: str | None) -> float | None:
    if not timestamp_a or not timestamp_b:
        return None
    a = datetime.strptime(timestamp_a, "%Y-%m-%d %H:%M:%S")
    b = datetime.strptime(timestamp_b, "%Y-%m-%d %H:%M:%S")
    return round((a - b).total_seconds() / 3600, 2)
