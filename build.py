#!/usr/bin/python

import sys
import subprocess
import pynt

@pynt.task()
def apidoc():
    """
    Generate API documentation using epydoc.
    """
    subprocess.call(["epydoc","--config","epydoc.config"])
    
@pynt.task()
def test(*args):
    """
    Run unit tests.
    """
    subprocess.call(["py.test"] + list(args))
    
if __name__ == "__main__":
    pynt.build(sys.modules[__name__],sys.argv[1:])
