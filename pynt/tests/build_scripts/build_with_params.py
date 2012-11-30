#!/usr/bin/python

import sys
from ... import _pynt

tasks_run = []
    
@_pynt.task()
def clean(directory='/tmp'):
    tasks_run.append('clean[%s]' % directory)

    
@_pynt.task(clean)
def html():
    tasks_run.append('html')


@_pynt.task()
def tests(*test_names):
    tasks_run.append('tests[%s]' % ','.join(test_names))


@_pynt.task(clean)
def copy_file(from_, to, fail_on_error='True'):
    tasks_run.append('copy_file[%s,%s,%s]' % (from_, to, fail_on_error))


@_pynt.task(clean)
def start_server(port='80', debug='True'):
    tasks_run.append('start_server[%s,%s]' % (port, debug))

@_pynt.task(clean)
def append_to_file(file, contents):
    tasks_run.append('append_to_file[%s,%s]' % (file, contents))

@_pynt.task()
def echo(*args,**kwargs):
    args_str = []
    if args:
        args_str.append(','.join(args))
    if kwargs:
        args_str.append(','.join("%s=%s" %  item for item in kwargs.items()))

    tasks_run.append('echo[%s]' % ','.join(args_str))


if __name__ == "__main__":
    _pynt.build(sys.modules[__name__],sys.argv[1:])
