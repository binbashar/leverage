import sys
from ... import _pynt

tasks_run = []

@_pynt.task()
def clean():
    tasks_run.append("clean")

@_pynt.task(clean)
def html():
    'Generate HTML.'
    tasks_run.append("html")

@_pynt.task(clean, ignore=True)
def images():
    """Prepare images.

    Should be ignored."""

    raise Exception("This task should have been ignored.")

@_pynt.task(clean,html,images)
def android():
    "Package Android app."

    tasks_run.append('android')
    
if __name__ == "__main__":
    _pynt.build(sys.modules[__name__],sys.argv[1:])
