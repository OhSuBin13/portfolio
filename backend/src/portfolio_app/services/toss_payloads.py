import math
from typing import Any


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def required_text(value: Any, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(message)
    return text


def positive_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(message)
    return number


def non_negative_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(message)
    return number
