import re
import sys
import pytest
from pathlib import Path
from importlib import util

from leverage.leverage import _terminate
from leverage.leverage import _get_tasks
from leverage.leverage import _print_version
from leverage.leverage import _load_build_script
from leverage.leverage import _prepare_tasks_to_run
from leverage.leverage import TaskNotFoundError
from leverage.leverage import MalformedTaskArgumentError


_BUILD_SCRIPTS = Path("./tests/build_scripts/").resolve()
BUILD_SCRIPT = _BUILD_SCRIPTS / "simple_build.py"


def test__load_build_script():
    module = _load_build_script(build_script=BUILD_SCRIPT)
    
    # All the important bits are extracted
    assert module["name"] == BUILD_SCRIPT.name
    assert len(module["tasks"]) == 1
    assert module["tasks"][0].name == "hello"
    assert module["__DEFAULT__"] is None
    
    # Module is globally available
    assert BUILD_SCRIPT.stem in sys.modules
    del sys.modules[BUILD_SCRIPT.stem]


def test__get_tasks():
    spec = util.spec_from_file_location(name=BUILD_SCRIPT.stem,
                                        location=BUILD_SCRIPT)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    tasks = _get_tasks(module=module)
    assert len(tasks) == 1
    assert tasks[0].name == "hello"


@pytest.mark.parametrize(
    "input_task",
    [
        "task1\[",
        "task1\[arg,",
        "arg2,",
        "val2\]"
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


def test__prepare_tasks_to_run():
    module = _load_build_script(build_script=BUILD_SCRIPT)

    tasks_to_run = _prepare_tasks_to_run(module, input_tasks=["hello[arg1, kwarg1=val1]"])

    assert len(tasks_to_run) == 1
    task, args, kwargs = tasks_to_run[0]
    assert task.name == "hello"
    assert args == ["arg1"]
    assert kwargs == {"kwarg1": "val1"}

    del sys.modules[BUILD_SCRIPT.stem]


def test__print_version(caplog):
    with pytest.raises(SystemExit) as sysexit:
        _print_version()

    assert sysexit.value.code == 0
    version = caplog.messages[0]
    assert re.match(r"^leverage \d+.\d+.\d+$", version)


def test__terminate(caplog):
    with pytest.raises(SystemExit) as sysexit:
        _terminate(error_message="Oops, something went wrong.")

    assert sysexit.value.code == 1
    error_message = caplog.messages[0]
    assert error_message == "Oops, something went wrong. Exiting."
