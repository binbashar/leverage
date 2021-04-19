import pytest

from leverage.task import task
from leverage.task import Task
from leverage.task import NotATaskError
from leverage.task import MissingParensInDecoratorError


def some_task(*args, **kwargs):
    """ A task. """
    pass


def _some_dependency(*args, **kwargs):
    """ A dependency. """
    pass
some_dependency = Task(task=_some_dependency)


@pytest.mark.parametrize(
    "potential_task, dependencies",
    [
        (some_task, [some_dependency]),
        (some_task, [])
    ]
)
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

    with pytest.raises(NotATaskError,
                       match=(r"Dependencies _some_dependency, SomeClass are not tasks. "
                              r"They all must be functions decorated with the `@task\(\)` decorator.")):
        @task(_some_dependency, SomeClass)
        def other_task():
            pass


def test_task_decorator_checks_for_missing_parens():
    with pytest.raises(MissingParensInDecoratorError,
                       match="Possible parentheses missing in function `other_task` decorator."):
        @task
        def other_task():
            pass
