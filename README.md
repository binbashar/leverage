[BinBash Inc](https://github.com/binbashar)

# Leverage CLI: An alternative to Makefiles that are used for running tasks.

## Features
* Easy to learn.
* Build tasks are just python functions.
* Manages dependencies between tasks.
* Automatically generates a command line interface.
* Rake style param passing to tasks
* Supports python >= 3.6


## Differences with Pynt
At first we adopted Pynt as a replacement tool for our Makefiles which were growing large and becoming to repetitive and thus harder to maintain. We also needed a better programming language than that provided by Makefiles. Pynt provided what we needed.

Even though most of the core functionality is still there, we did introduce the following changes:
* A build file is not only looked up in the current working directory but also in parent directories.
* Custom modules were added next to the core module and more are expected to be added this year.
* A build config file (build.env) is optionally supported (and can also be located in current working directory or in parent directories) in order to have configuration values that are used by the build script or by the supporting modules.

## Installation
You can install leverage from the Python Package Index (PyPI) or from source.
First, make sure your Python version is 3.6 or higher. Then install via pip:
```bash
$ pip install leverage
```


## Getting started
* Define a build script -- Check the example below.
* Go to the same directory where the build script is (or to a child directory of that)
* Run `leverage` so it can discover the build script, parse it and show any tasks defined
* Optionally define build config file (build.env)
* Optionally create modules and import them from your build script


## Example build script
The build script is written in pure Python and Leverage takes care of managing
any dependencies between tasks and generating a command line interface.

### build.py
```python
#!/usr/bin/python3

import sys
from leverage import task

@task()
def clean():
    '''Clean build directory.'''
    print 'Cleaning build directory...'

@task()
def _copy_resources():
    '''Copy resource files. This is a private task and will not be listed.'''
    print('Copying resource files')

@task(clean, _copy_resources)
def html(target='.'):
    '''Generate HTML.'''
    print 'Generating HTML in directory "%s"' %  target

@task(clean, _copy_resources, ignore=True)
def images():
    '''Prepare images.'''
    print 'Preparing images...'

@task(html,images)
def start_server(server='localhost', port = '80'):
    '''Start the server'''
    print 'Starting server at %s:%s' % (server, port)

@task(start_server) #Depends on task with all optional params
def stop_server():
    print 'Stopping server....'

@task()
def copy_file(src, dest):
    print 'Copying from %s to %s' % (src, dest)

@task()
def echo(*args,**kwargs):
    print args
    print kwargs

# Default task (if specified) is run when no task is specified in the command line
# make sure you define the variable __DEFAULT__ after the task is defined
# A good convention is to define it at the end of the module
# __DEFAULT__ is an optional member

__DEFAULT__=start_server
```

### Writing tasks
Writing build tasks is really simple, all you need to know is the @task decorator. Tasks are just regular Python functions marked with the ``@task()`` decorator. Dependencies are specified with ``@task()`` too.
Tasks can be ignored with the ``@task(ignore=True)``. Disabling a task is an useful feature to have in situations where you have one task that a lot of other tasks depend on and you want to quickly remove it from the dependency chains of all the dependent tasks.
Note that any task whose name starts with an underscore(``_``) will be considered private.
Private tasks are not listed, but they can still be run with ``leverage _private_task_name``

### Running Leverage tasks
The command line interface and help is automatically generated. Task descriptions
are extracted from function docstrings.

You can list the tasks available as follows:
```bash
$ leverage -l
Tasks in build file build.py:
  clean                       Clean build directory.
  copy_file
  echo
  html                        Generate HTML.
  images           [Ignored]  Prepare images.
  start_server     [Default]  Start the server
  stop_server

Powered by Leverage 0.0.10 - A Lightweight Python Build Tool based on Pynt.
```

Note: keep in mind that the flag `-l` is needed here because a default task is set, otherwise passing such flag would not be needed.

Task dependencies between tasks are taken care of. In the following case `html` depends on `clean` and `_copy_resources` so those 2 will run before the former task:
```bash
$ leverage html
[ build.py - Starting task "clean" ]
Cleaning build directory...
[ build.py - Completed task "clean" ]
[ build.py - Starting task "_copy_resources" ]
Copying resource files
[ build.py - Completed task "_copy_resources" ]
[ build.py - Starting task "html" ]
Generating HTML in directory "."
[ build.py - Completed task "html" ]
```


Tasks can accept parameters from commandline:
```bash
$ leverage copy_file["/path/to/foo","path_to_bar"]
[ build.py - Starting task "copy_file" ]
Copying from /path/to/foo to path_to_bar
[ build.py - Completed task "copy_file" ]
```

Tasks can also accept keyword arguments:
```bash
$ leverage echo[hello,world,foo=bar,blah=123]
[ build.py - Starting task "echo" ]
('hello', 'world')
{'foo': 'bar', 'blah': '123'}
[ build.py - Completed task "echo" ]
```

### Organizing build scripts
You can break up your build files into modules and simple import them into your main build file.

```python
from deploy_tasks import *
from test_tasks import functional_tests, report_coverage
```


## Known issues

### Zsh Glob Patterns: "zsh: no matches found"
If you use `zsh` as your shell and you need to pass arguments to a task in this way: `leverage state_import["import.json"]`, or this other way: `leverage outout["-json"]`, you might get the an error like this one: `zsh: no matches found: output[-json]`
The problem in that case has to do with with the square brackets as zhs has glob patterns enabled by default which causes every input to be interpreted like that.

The are a few workarounds to help with this:
1. Escape the square brackets: `leverage state_import\["import.json"\]`
2. Enclose the entire task between double quotes: `leverage "state_import[import.json]"`
3. Disable glob patterns: `noglob leverage state_import["import.json"]`
4. An improvement over the last point is to create an alias such as this one: `alias leverage='noglob leverage'`

## Running Tests
To run unit tests pytest is the tool of choice, and the required dependencies are available in the corresponding `dev-requirements.txt`.

Integration tests are implemented using [bats](https://github.com/bats-core/bats-core/). Bear in mind that bats tests are meant to be run in a throwaway environment since they perform filesystem manipulations and installation and removal of packages, and the cleanup may not be completely thorough.

### Manually
Unit tests:
```bash
pip3 install -r dev-requirements.txt
python3 -m pytest
```
Integration tests:
```bash
bats -r tests/bats
```
### Using docker image
A Dockerfile suited for running all tests is provided along with useful Makefile targets.

To build such image run `make build-image`.

To run all tests `make tests`. Alternatively `make test-unit` or `make test-int` for unit or integration tests respectively.

## Release Process
* On every PR, a Github Action workflow is triggered to create/update a release draft.
* The version number is determined by the labels of those PRs (major, minor, fix).
* The release draft has to be manually published. This allows for any number of PR (features, fixes) to make the cut.
* Once a release is published, another workflow is triggered to create and push the package to PyPi.


## Contributors/Contributing
* Leverage CLI is based on Pynt: https://github.com/rags/pynt
* Calum J. Eadie - pynt is preceded by and forked from [microbuild](https://github.com/CalumJEadie/microbuild), which was created by [Calum J. Eadie](https://github.com/CalumJEadie).


## License
Leverage CLI is licensed under a [MIT license](http://opensource.org/licenses/MIT)
