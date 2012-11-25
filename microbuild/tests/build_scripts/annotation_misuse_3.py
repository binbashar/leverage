from ... import microbuild

@microbuild.task()
def clean():
    pass
    
# Referring to clean by name rather than reference.
@microbuild.task(1234)
def html():
    pass
