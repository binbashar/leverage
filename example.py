#!/usr/bin/python
from pynt import task

@task()
def clean():
    '''Clean build directory.'''
    print('Cleaning build directory...')

@task(clean)
def html(target='.'):
    '''Generate HTML.'''
    print(('Generating HTML in directory "%s"' %  target))


@task(clean, ignore=True)
def images():
    '''Prepare images.'''
    print('Preparing images...')

@task(html,images)
def start_server(server='localhost', port = '80'):
    '''Start the server'''
    print(('Starting server at %s:%s' % (server, port)))

@task(start_server) #Depends on task with all optional params
def stop_server():
    print('Stopping server....')

@task()
def copy_file(src, dest):
    print(('Copying from %s to %s' % (src, dest)))

@task()
def echo(*args,**kwargs):
    print(args)
    print(kwargs)
    
# Default task (if specified) is run when no task is specified in the command line
# make sure you define the variable __DEFAULT__ after the task is defined
# A good convention is to define it at the end of the module
# __DEFAULT__ is an optional member

__DEFAULT__=start_server
