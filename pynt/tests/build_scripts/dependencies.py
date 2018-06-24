from pynt import task


@task()
def clean():
    """Clean build directory."""

    print("clean")

@task(clean)
def html():
    """Generate HTML."""
    print("html")

@task(clean)
def images():
    """Prepare images."""

    print("images")

@task()
def _common_private_task():
    """Package iOS app."""
    print("os agnostic task")

@task(clean, html, images, _common_private_task)
def android():
    """Package Android app."""
    print("android")

@task(clean, html, images, _common_private_task)
def ios():
    """Package iOS app."""
    print("ios")


def some_utility_method():
    """Some utility method."""
    print("some utility method")
