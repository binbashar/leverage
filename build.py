#!/usr/bin/python

import sys
import subprocess
from pynt import task, build

@task()
def apidoc():
    """
    Generate API documentation using epydoc.
    """
    subprocess.call(["epydoc","--config","epydoc.config"])
    
@task()
def test(*args):
    """
    Run unit tests.
    """
    subprocess.call(["py.test"] + list(args))

@task()
def generate_rst():
    
    subprocess.call(['pandoc', '-f', 'markdown', '-t', 'rst', '-o', 'README.rst', 'README.md'])

@task(generate_rst)
def upload():
    subprocess.call(['python', 'setup.py', 'bdist', '--formats', 'wininst,gztar', 'upload'])

if __name__ == "__main__":
    build(sys.modules[__name__],sys.argv[1:])
