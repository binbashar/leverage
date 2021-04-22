from leverage import task
from leverage import conf

@task()
def confhello():
    values = conf.load()
    use_verbose_hello = values.get("USE_VERBOSE_HELLO", "true").lower() == "true"
    
    if use_verbose_hello:
        print("This is a way too long hello for anyone to say")
    else:
        print("Hello")
