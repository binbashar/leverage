#!/usr/bin/python

from pynt import task

from test_module import do_stuff

@task()
def work():
    do_stuff()