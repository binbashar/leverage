"""
Value casting utilities.
"""

from typing import Any

import yaml


def as_bool(value: str) -> Any:
    """Return the boolean representation of ``value`` if possible."""
    try:
        parsed = yaml.safe_load(value)
        if isinstance(parsed, bool):
            return parsed
    except yaml.YAMLError:
        pass
    return value


def as_int(value: str) -> Any:
    """Return the integer representation of ``value`` if possible."""
    try:
        return int(value)
    except ValueError:
        return value


def as_float(value: str) -> Any:
    """Return the float representation of ``value`` if possible."""
    try:
        return float(value)
    except ValueError:
        return value


def cast_value(value: str) -> Any:
    """Try to cast ``value`` to bool, int or float using the helper functions
    :func:`as_bool`, :func:`as_int` and :func:`as_float`.

    Args:
        value (str): Value to cast.

    Returns:
        Any: The value converted to its apparent type or the original string.
    """
    value = as_bool(value)
    if isinstance(value, str):
        value = as_int(value)
    if isinstance(value, str):
        value = as_float(value)

    return value
