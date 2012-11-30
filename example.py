#!/usr/bin/python

import sys
from pynt import task,ignore,build

@task()
def clean():
    """Clean build directory."""
    print "Cleaning build directory..."

@task(clean)
def html():
    """Generate HTML."""
    print "Generating HTML..."

@ignore
@task(clean)
def images():
    """Prepare images."""
    print "Preparing images..."

@task(html,images)
def android():
    """Package Android app."""
    print "Packaging android app..."
    
if __name__ == "__main__":
    build(sys.modules[__name__],sys.argv[1:])
