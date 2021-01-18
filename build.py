from leverage import task
from leverage import conf

@task()
def hello():
    '''Say hello.'''
    print("Hello")

@task()
def config():
    '''Show config'''
    print(conf.load())
