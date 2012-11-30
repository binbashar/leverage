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
def test():
    """
    Run unit tests.
    """
    subprocess.call(["python","-m","pynt.tests.test_pynt"])
    #subprocess.call(["python","-m","pynt.tests.build_scripts.dependancies","-h"])
    #subprocess.call(["python","-m","pynt.tests.build_scripts.dependancies","android"])
    #subprocess.call(["python","-m","pynt.tests.build_scripts.runtime_error","android"])
    
if __name__ == "__main__":
    pynt.build(sys.modules[__name__],sys.argv[1:])
