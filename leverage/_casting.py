"""
Value casting utilities.
"""

from typing import Any

import yaml


def cast_value(value: str) -> Any:
    """Try to cast a string to bool, int or float using ``PyYAML`` for boolean
    parsing and falling back to ``int``/``float`` conversion.

    Args:
        value (str): Value to cast.

    Returns:
        Any: The value converted to its apparent type or the original string.
    """
    try:
        parsed = yaml.safe_load(value)
        if isinstance(parsed, bool):
            return parsed
    except yaml.YAMLError:
        pass

    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value
