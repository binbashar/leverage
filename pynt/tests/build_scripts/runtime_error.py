"""
Build script with a runtime error.
"""

import sys
from ... import _pynt

@_pynt.task()
def images():
    """Prepare images. Raises IOError."""
    global ran_images
    ran_images = True
    raise IOError

@_pynt.task(images)
def android():
    """Package Android app."""
    global ran_android
    print "android"
    ran_android = True
    
if __name__ == "__main__":
    _pynt.build(sys.modules[__name__],sys.argv[1:])
