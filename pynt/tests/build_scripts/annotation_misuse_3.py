from ... import _pynt

@_pynt.task()
def clean():
    pass
    
# Referring to clean by name rather than reference.
@_pynt.task(1234)
def html():
    pass
