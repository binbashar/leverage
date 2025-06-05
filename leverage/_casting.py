"""
Value casting utilities.
"""

from typing import Any


def cast_value(value: str) -> Any:
    """Try to cast a string to bool, int or float.

    Args:
        value (str): Value to cast.

    Returns:
        Any: The value converted to its apparent type or the original string.
    """
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value
