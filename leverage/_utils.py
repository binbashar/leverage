"""
    Tasks displaying utilities.
"""
from operator import attrgetter

import click

from leverage import __version__


_CREDIT_LINE = f"Powered by Leverage {__version__}"
_IGNORED = "Ignored"
_DEFAULT = "Default"


def _list_tasks(module):
    """ Print all non-private tasks in a neat table-like format.
    Indicates whether the task is ignored and/or if it is the default one.

    Args:
        module (dict): Dictionary containing all tasks and the module name
    """
    visible_tasks = [task for task in module["tasks"] if not task.is_private]

    if visible_tasks:
        # Header
        click.echo(f"Tasks in build file `{module['name']}`:\n")

        tasks_grid = []

        for task in sorted(visible_tasks, key=attrgetter("name")):
            # Form the attrs column values
            task_attrs = []
            if task == module["__DEFAULT__"]:
                task_attrs.append(_DEFAULT)
            if task.is_ignored:
                task_attrs.append(_IGNORED)
            task_attrs = f"[{','.join(task_attrs)}]" if task_attrs else ""
            # Split multiline docstrings to be able to handle them as a column
            doc_lines = task.doc.splitlines()

            tasks_grid.append((task.name, task_attrs, doc_lines))

        name_column_width = max(len(name) for name, _, _ in tasks_grid)
        attr_column_width = max(len(attr) for _, attr, _ in tasks_grid)

        # Body
        for name, attr, doc in tasks_grid:

            click.echo(f"  {name:<{name_column_width}}  {attr: ^{attr_column_width}}\t{doc[0]}")
            # Print the remaining lines of the dosctring with the correct indentation
            for doc_line in doc[1:]:
                click.echo(f"    {'': <{name_column_width + attr_column_width}}\t{doc_line}")

        # Footer
        click.echo(f"\n{_CREDIT_LINE}")

    else:
        click.echo("  No tasks found or no build script present in current directory.")
