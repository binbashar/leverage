from ... import _pynt

@_pynt.task()
def clean():
    pass
    
# Should be marked as task.
def html():
    pass

# References a non task.
@_pynt.task(clean,html)
def android():
    pass
