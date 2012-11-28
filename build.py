#!/usr/bin/python

import sys
import subprocess
import microbuild

@microbuild.task()
def apidoc():
    """
    Generate API documentation using epydoc.
    """
    subprocess.call(["epydoc","--config","epydoc.config"])
    
@microbuild.task()
def test():
    """
    Run unit tests.
    """
    subprocess.call(["python","-m","microbuild.tests.microbuild"])
    #subprocess.call(["python","-m","microbuild.tests.build_scripts.dependancies","-h"])
    #subprocess.call(["python","-m","microbuild.tests.build_scripts.dependancies","android"])
    #subprocess.call(["python","-m","microbuild.tests.build_scripts.runtime_error","android"])
    
if __name__ == "__main__":
    microbuild.build(sys.modules[__name__],sys.argv[1:])
