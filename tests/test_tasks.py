from importlib import util

import pytest
from click.exceptions import Exit

from leverage.tasks import task
from leverage.tasks import Task
from leverage.tasks import load_tasks
from leverage.tasks import _get_tasks
from leverage.tasks import _load_build_script
from leverage.tasks import NotATaskError
from leverage.tasks import MissingParensInDecoratorError
from leverage._internals import Module

from .conftest import BUILD_SCRIPTS
from .conftest import BUILD_SCRIPT


def some_task(*args, **kwargs):
    """A task."""
    pass


def _some_dependency(*args, **kwargs):
    """A dependency."""
    pass


some_dependency = Task(task=_some_dependency)


@pytest.mark.parametrize("potential_task, dependencies", [(some_task, [some_dependency]), (some_task, [])])
def test_task_decorator(potential_task, dependencies):
    task_factory = task(*dependencies)
    task_obj = task_factory(potential_task)

    assert isinstance(task_obj, Task)
    assert task_obj.task == potential_task
    assert task_obj.name == potential_task.__name__
    assert task_obj.doc == potential_task.__doc__
    assert task_obj.dependencies == dependencies


def test_task_decorator_checks_dependencies_are_tasks():
    class SomeClass:
        pass

    with pytest.raises(
        NotATaskError,
        match=(
            r"Dependencies _some_dependency, SomeClass are not tasks. "
            r"They all must be functions decorated with the `@task\(\)` decorator."
        ),
    ):

        @task(_some_dependency, SomeClass)
        def other_task():
            pass


def test_task_decorator_checks_for_missing_parens():
    with pytest.raises(
        MissingParensInDecoratorError, match="Possible parentheses missing in function `other_task` decorator."
    ):

        @task
        def other_task():
            pass


def test_load_tasks_no_build_script(monkeypatch):
    monkeypatch.setattr("leverage.tasks.get_build_script_path", lambda filename: None)

    module = load_tasks()
    assert module == Module()


def test_load_tasks(monkeypatch):
    monkeypatch.setattr("leverage.tasks.get_build_script_path", lambda filename: BUILD_SCRIPT.as_posix())
    spec = util.spec_from_file_location(name=BUILD_SCRIPT.stem, location=BUILD_SCRIPT)
    expected_module = util.module_from_spec(spec)
    spec.loader.exec_module(expected_module)
    expected_module = Module(name=BUILD_SCRIPT.name, tasks=_get_tasks(module=expected_module))

    module = load_tasks(build_script_filename=BUILD_SCRIPT.name)
    assert module == expected_module


def test__load_build_script():
    module = _load_build_script(build_script=BUILD_SCRIPT)

    # All the important bits are extracted
    assert module.name == BUILD_SCRIPT.name
    assert len(module.tasks) == 1
    assert module.tasks[0].name == "hello"
    assert module.default_task is None


def test__load_build_script_captures_module_exceptions(with_click_context):
    bad_build_script = BUILD_SCRIPTS / "simple_build_bad_syntax.py"

    with pytest.raises(Exit):
        _load_build_script(build_script=bad_build_script)


def test__get_tasks():
    spec = util.spec_from_file_location(name=BUILD_SCRIPT.stem, location=BUILD_SCRIPT)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    tasks = _get_tasks(module=module)
    assert len(tasks) == 1
    assert tasks[0].name == "hello"
