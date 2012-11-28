#!/usr/bin/python

import sys
from ... import _microbuild

@_microbuild.task()
def clean():
    """Clean build directory."""

    print "clean"

@_microbuild.task()
def html():
    """Generate HTML."""
    
    print "html"

@_microbuild.task()
def images():
    """Prepare images."""

    print "images"

@_microbuild.task()
def android():
    """Package Android app."""

    print "android"

@_microbuild.task()
def ios():
    """Package iOS app."""

    print "ios"
    
def some_utility_method():
    """Some utility method."""

    print "some utility method"
    
if __name__ == "__main__":
    _microbuild.build(sys.modules[__name__],sys.argv[1:])
