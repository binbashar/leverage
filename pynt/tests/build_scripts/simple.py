#!/usr/bin/python

import sys
from ... import _pynt

@_pynt.task()
def clean():
    """Clean build directory."""

    print "clean"

@_pynt.task()
def html():
    """Generate HTML."""
    
    print "html"

@_pynt.task()
def images():
    """Prepare images."""

    print "images"

@_pynt.task()
def android():
    """Package Android app."""

    print "android"

@_pynt.task()
def ios():
    """Package iOS app."""

    print "ios"
    
def some_utility_method():
    """Some utility method."""

    print "some utility method"
    
if __name__ == "__main__":
    _pynt.build(sys.modules[__name__],sys.argv[1:])
