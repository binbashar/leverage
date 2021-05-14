import sys
import pytest

from click import ClickException

from leverage.leverage import _load_build_script
from leverage.modules.run import _prepare_tasks_to_run
from leverage.modules.run import TaskNotFoundError
from leverage.modules.run import MalformedTaskArgumentError

from ..conftest import BUILD_SCRIPT


@pytest.mark.parametrize(
    "input_task",
    [
        r"task1\[",
        r"task1\[arg,",
        r"arg2,",
        r"val2\]"
    ]
)
def test__prepare_tasks_to_run_checks_input_format(input_task):
    # Remove escape sequences before using as input
    _input_task = "".join(input_task.split("\\"))

    with pytest.raises(MalformedTaskArgumentError,
                       match=f"Malformed task argument in `{input_task}`."):
        _prepare_tasks_to_run(module=None, input_tasks=[_input_task])


def test__prepare_tasks_to_run_checks_task_existence():
    module = _load_build_script(build_script=BUILD_SCRIPT)

    with pytest.raises(TaskNotFoundError,
                       match="Unrecognized task `nothello`."):
        _prepare_tasks_to_run(module=module, input_tasks=["nothello"])

    del sys.modules[BUILD_SCRIPT.stem]


@pytest.mark.parametrize(
    "input_task, message",
    [
        ( # Bad arguments order
            "hello[arg1,arg2,kwarg1=val1,arg3,kwarg2=val2]",
            "Positional argument `arg3` from task `hello` cannot follow a keyword argument."
        ),
        ( # Duplicated keyword argument
            "hello[arg1,kwarg1=val1,kwarg1=val1]",
            "Duplicated keyword argument `kwarg1` in task `hello`."
        )
    ]
)
def test__prepare_tasks_to_run_handles_bad_arguments(input_task, message):
    with pytest.raises(ClickException, match=message):
        _prepare_tasks_to_run(module=None, input_tasks=[input_task])


def test__prepare_tasks_to_run():
    module = _load_build_script(build_script=BUILD_SCRIPT)

    tasks_to_run = _prepare_tasks_to_run(module, input_tasks=["hello[arg1, kwarg1=val1]"])

    assert len(tasks_to_run) == 1
    task, args, kwargs = tasks_to_run[0]
    assert task.name == "hello"
    assert args == ["arg1"]
    assert kwargs == {"kwarg1": "val1"}

    del sys.modules[BUILD_SCRIPT.stem]
