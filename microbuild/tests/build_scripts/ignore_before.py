import sys
from ... import _microbuild

@_microbuild.task()
def clean():
    """Clean build directory."""

    print "clean"

@_microbuild.task(clean)
def html():
    """Generate HTML."""
    
    print "html"

@_microbuild.ignore
@_microbuild.task(clean)
def images():
    """Prepare images. Should be ignored."""

    raise Exception("This task should have been ignored.")

@_microbuild.task(clean,html,images)
def android():
    """Package Android app."""

    print "android"
    
if __name__ == "__main__":
    _microbuild.build(sys.modules[__name__],sys.argv[1:])
