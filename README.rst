===========================================
microbuild - Lightweight Python Build Tool.
===========================================

Calum J. Eadie (www.calumjeadie.com)

Features
========

* Really quick to learn.
* Manages dependancies between tasks.
* Automatically generates a command line interface.

Example
=======

The build script is written in pure Python and microbuild takes care of managing
any dependancies between tasks and generating a command line interface.

Tasks are just regular Python functions marked with the ``@task()`` decorator. Dependancies
are specified with ``@task()`` too. Tasks can be ignored with the ``@ignore`` decorator.

After defining all tasks ``build(sys.modules[__name__],sys.argv[1:])`` is called to
run the build.

::

    # example.py
    import sys
    from microbuild.microbuild import task,ignore,build

    @task()
    def clean():
        """Clean build directory."""
        print "Cleaning build directory..."

    @task(clean)
    def html():
        """Generate HTML."""
        print "Generating HTML..."

    @ignore
    @task(clean)
    def images():
        """Prepare images."""
        print "Preparing images..."

    @task(html,images)
    def android():
        """Package Android app."""
        print "Packaging android app..."
        
    if __name__ == "__main__":
        build(sys.modules[__name__],sys.argv[1:])
            
The command line interface and help is automatically generated. Task descriptions
are extracted from function docstrings.

::
    
    $ ./example.py -h
    usage: example.py [-h] task

    positional arguments:
      task        perform specified task and all it's dependancies

    optional arguments:
      -h, --help  show this help message and exit

    tasks:
      android     Package Android app.
      clean       Clean build directory.
      html        Generate HTML.
      images      Prepare images.
          
Dependancies between tasks are taken care of too.

::
 
    $ ./example.py android
    [ example.py - Starting task "clean" ]
    Cleaning build directory...
    [ example.py - Completed task "clean" ]
    [ example.py - Starting task "html" ]
    Generating HTML...
    [ example.py - Completed task "html" ]
    [ example.py - Ignoring task "images" ]
    [ example.py - Starting task "android" ]
    Packaging android app...
    [ example.py - Completed task "android" ]

Partial task names are enough to execute the task, as long as the partial name is not ambigious. You can specify multiple tasks o run in the commandline. Again the dependencies are taken taken care of.

::
    $ python example.py cle ht cl 
    [ example.py - Starting task "clean" ]
    Cleaning build directory...
    [ example.py - Completed task "clean" ]
    [ example.py - Starting task "html" ]
    Generating HTML...
    [ example.py - Completed task "html" ]
    [ example.py - Starting task "clean" ]
    Cleaning build directory...
    [ example.py - Completed task "clean" ]

The 'html' task dependency 'clean' is run only once. But clean can be explicitly run again later.

Installation
============

You can install microbuild from the Python Package Index (PyPI) or from source.

Using pip::

    $ pip microbuild

Using easy_install::

    $ easy_install microbuild
    
License
=======

microbuild is licensed under a MIT license. See `LICENSE.txt`_.

.. _LICENSE.txt: https://github.com/CalumJEadie/microbuild/blob/master/LICENSE.txt
