import pytest

from leverage._parsing import parse_task_args
from leverage._parsing import InvalidArgumentOrderError
from leverage._parsing import DuplicateKeywordArgumentError


@pytest.mark.parametrize(
    "arguments, expected_args, expected_kwargs",
    [
        ("arg1, 2, 3.5 ", ["arg1", 2, 3.5], {}),  # Cast positional arguments
        (  # All keyworded arguments
            "kwarg1=true,kwarg2 = val2, kwarg3 = 3 ",
            [],
            {"kwarg1": True, "kwarg2": "val2", "kwarg3": 3},
        ),
        ("arg1, arg2, kwarg1=/val/1,kwarg2 = val2", ["arg1", "arg2"], {"kwarg1": "/val/1", "kwarg2": "val2"}),  # Both
        # Edge cases for casting
        ("1e10, inf, nan", [1e10, float('inf'), float('nan')], {}),
        ("007, 0123", [7, 123], {}),  # Leading zeros
        ("kwarg1=1.0,kwarg2=0.0", [], {"kwarg1": 1.0, "kwarg2": 0.0}),  # Ensure float casting
        # Boolean edge cases
        ("True, FALSE, yes, no", [True, False, True, False], {}),
        (
            "kwarg1=TRUE,kwarg2=false,kwarg3=1,kwarg4=0",
            [],
            {"kwarg1": True, "kwarg2": False, "kwarg3": 1, "kwarg4": 0},
        ),
        (None, [], {}),  # No arguments
    ],
)
def test__parse_args(arguments, expected_args, expected_kwargs):
    args, kwargs = parse_task_args(arguments=arguments)
    for received, expected in zip(args, expected_args):
        if isinstance(expected, float) and expected != expected:  # NaN check
            assert received != received
        else:
            assert received == expected

    assert kwargs == expected_kwargs


@pytest.mark.parametrize(
    "arguments, exception, message",
    [
        (  # Positional argument after a keyworded argument
            "arg1,arg2,kwarg1=val1,arg3,kwarg2=val2",
            InvalidArgumentOrderError,
            "Positional argument `arg3` from task `{task}` cannot follow a keyword argument.",
        ),
        (  # Duplicated keyworded argument
            "arg1,kwarg1=val1,kwarg1=val1",
            DuplicateKeywordArgumentError,
            "Duplicated keyword argument `kwarg1` in task `{task}`.",
        ),
    ],
)
def test__parse_args_incorrect_arguments(arguments, exception, message):
    with pytest.raises(exception, match=message):
        parse_task_args(arguments=arguments)
