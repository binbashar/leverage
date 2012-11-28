from ... import _microbuild

# Uses @_microbuild.task form instead of @_microbuild.task() form.
@_microbuild.task
def clean():
    pass
