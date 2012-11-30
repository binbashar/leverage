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
def images():
    """Prepare images."""

    print "images"

@_pynt.task(clean,html,images)
def android():
    """Package Android app."""

    print "android"

@_pynt.task(clean,html,images)
def ios():
    """Package iOS app."""

    print "ios"
    
def some_utility_method():
    """Some utility method."""

    print "some utility method"
    
if __name__ == "__main__":
    _pynt.build(sys.modules[__name__],sys.argv[1:])
