import sys
from ... import _pynt

@_pynt.task()
def clean():
    """Clean build directory."""

    print "clean"

@_pynt.task(clean)
def html():
    """Generate HTML."""
    
    print "html"

@_pynt.task(clean)
@_pynt.ignore
def images():
    """Prepare images. Should be ignored."""

    raise Exception("This task should have been ignored.")

@_pynt.task(clean,html,images)
def android():
    """Package Android app."""

    print "android"
    
if __name__ == "__main__":
    _pynt.build(sys.modules[__name__],sys.argv[1:])
