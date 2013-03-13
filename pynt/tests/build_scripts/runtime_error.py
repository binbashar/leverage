"""
Build script with a runtime error.
"""
from pynt import task


@task()
def images():
    """Prepare images. Raises IOError."""
    global ran_images
    ran_images = True
    raise IOError

@task(images)
def android():
    """Package Android app."""
    global ran_android
    print("android")
    ran_android = True

