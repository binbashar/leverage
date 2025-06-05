import math

import pytest

from leverage._casting import as_bool, as_int, as_float, cast_value


@pytest.mark.parametrize(
    "value, expected",
    [
        ("true", True),
        ("False", False),
        ("1", 1),
        ("-2", -2),
        ("3.14", 3.14),
        ("1e3", 1000.0),
        ("inf", float("inf")),
        ("nan", float("nan")),
        ("007", 7),
        ("0123", 123),
        ("foo", "foo"),
    ],
)
def test_cast_value(value, expected):
    result = cast_value(value)
    if isinstance(expected, float) and math.isnan(expected):
        assert math.isnan(result)
    else:
        assert result == expected


def test_helper_functions():
    assert as_bool("true") is True
    assert as_bool("no") is False
    assert as_int("42") == 42
    assert as_int("bar") == "bar"
    assert as_float("3.14") == 3.14
    assert as_float("not") == "not"
