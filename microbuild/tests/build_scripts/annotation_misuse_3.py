from ... import _microbuild

@_microbuild.task()
def clean():
    pass
    
# Referring to clean by name rather than reference.
@_microbuild.task(1234)
def html():
    pass
