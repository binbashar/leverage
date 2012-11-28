from ... import _microbuild

@_microbuild.task()
def clean():
    pass
    
# Should be marked as task.
def html():
    pass

# References a non task.
@_microbuild.task(clean,html)
def android():
    pass
