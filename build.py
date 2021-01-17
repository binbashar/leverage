from leverage import task
from leverage import terraform

@task()
def hello():
    '''Say hello.'''
    print("Hello")

@task()
def version():
    '''Print terraform version'''
    terraform.version()
