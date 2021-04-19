"""
    Task object definition and task creation decorator.
"""
from inspect import isfunction


class NotATaskError(ImportError):
    pass


class MissingParensInDecoratorError(ImportError):
    pass


def task(*dependencies, **options):
    """ Task decorator to mark functions in a build script as tasks to be performed.

    Raises:
        MissingParensInDecorator: When the decorator is most likely being used without parentheses
            on a function.
        NotATask: When any of the task dependencies is not a task.

    Returns:
        Task: the task to be run
    """
    # In
    # ```
    #     @task
    #     def func():
    #         pass
    # ```
    # `func` ends up passed as a dependency to the decorator and becomes indistinguishable from
    # ```
    #     @task(function_not_task)
    #     def func():
    #         pass
    # ```
    # where the dependency provided is a function and not a task. So the need of parentheses is
    # enforced through this check below
    if len(dependencies) == 1 and isfunction(dependencies[0]):
        raise MissingParensInDecoratorError("Possible parentheses missing in function "
                                            f"`{dependencies[0].__name__}` decorator.")

    not_tasks = [dependency.__name__
                 for dependency in dependencies
                 if not Task.is_task(dependency)]

    if not_tasks:
        raise NotATaskError(f"Dependencies {', '.join(not_tasks)} are not tasks. "
                        "They all must be functions decorated with the `@task()` decorator.")

    def _task(func):
        return Task(func, list(dependencies), options)

    return _task


class Task:
    """ Task to be run by Leverage, created from a function with the @task() decorator.
    A task which name starts with an underscore is considered private and, as such, not shown
    when tasks are listed, this can also be explicitly indicated in the decorator.
    An ignored task won't be ran by Leverage.
    """
    def __init__(self, task, dependencies, options):
        """ Task object initialization

        Args:
            task (function): Function to be called upon task execution.
            dependencies (list(Tasks)): List of tasks that must be performed before this
                task is executed.
            options (dict): Options regarding the task nature:
                - private (bool): Whether the task is private or not.
                - ignored (bool): When `True` the task won't be executed by Leverage.
        """
        self.task = task
        self.name = self.task.__name__
        self.doc = self.task.__doc__ or ""
        self.dependencies = dependencies
        self._private = self.name.startswith("_") or bool(options.get("private", False))
        self._ignored = bool(options.get("ignore", False))

    @classmethod
    def is_task(cls, obj):
        """ Whether the given object is a task or not """
        return isinstance(obj, cls)

    @property
    def is_private(self):
        """ Whether the task is private or not """
        return self._private

    @property
    def is_ignored(self):
        """ Whether the task is ignored or not """
        return self._ignored

    def __call__(self, *args, **kwargs):
        """ Execute the task """
        self.task(*args, **kwargs)
