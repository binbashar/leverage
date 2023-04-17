import pytest

from leverage._parsing import parse_task_args
from leverage._parsing import InvalidArgumentOrderError
from leverage._parsing import DuplicateKeywordArgumentError


@pytest.mark.parametrize(
    "arguments, expected_args, expected_kwargs",
    [
        ("arg1, arg2, arg3 ", ["arg1", "arg2", "arg3"], {}),  # All positional arguments
        (  # All keyworded arguments
            "kwarg1=/val/1,kwarg2 = val2, kwarg3 = val3 ",
            [],
            {"kwarg1": "/val/1", "kwarg2": "val2", "kwarg3": "val3"},
        ),
        ("arg1, arg2, kwarg1=/val/1,kwarg2 = val2", ["arg1", "arg2"], {"kwarg1": "/val/1", "kwarg2": "val2"}),  # Both
        (None, [], {}),  # No arguments
    ],
)
def test__parse_args(arguments, expected_args, expected_kwargs):
    args, kwargs = parse_task_args(arguments=arguments)

    assert args == expected_args
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
