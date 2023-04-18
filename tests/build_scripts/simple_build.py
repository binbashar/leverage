from leverage import task


@task()
def hello():
    """Say hello."""
    print("Hello")
