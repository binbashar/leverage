Changes
=======
0.8.2 - 23/06/2018
------------------
* private tasks. Any tasks that start with an underscore(_) are private by convention.


0.8.1 - 02/09/2013
------------------
* Enabling extensions

0.8.0 - 02/09/2013
------------------
* Support for specifying a default task with __DEFAULT__ variable
* pynt -v (--version) for displays version info
* pynt -l lists tasks in alphabetical order

0.7.1 - 17/03/2013
------------------
* Migrated pynt to work on python 3.x. pynt still works on 2.7.
* pynt version now displayed as part of help output.

0.7.0 - 16/02/2013
------------------

* New commandline interface. Distribution now includes 'pynt' executable.
* 'build.py' is the default build file.
* Build files no longer need "if main" construct.
* pynt no longer exposes build method. This is a backward incompatible change.


0.6.0 - 17/12/2012
------------------

* Simplified ignoring tasks. ignore a keyword param for task and not a separate decorator. [This change is NOT backward compatible!!!]
* Added support for listing tasks
* Improved help


0.5.0 - 01/12/2012
------------------

* Ability to pass params to tasks.
* Major rewrite and flattening the package hierarchy.

0.4.0 - 17/11/2012
------------------

* Support for running multiple tasks from commandline.
* Ability to run tasks by typing in just the first few unambigious charecters.


Changes before forking from microbuild
======================================

0.3.0 - 18/09/2012
------------------

* Fixed bug in logging. No longer modifies root logger.
* Added ignore functionality.
* Extended API documentation.

0.2.0 - 29/08/2012
------------------

* Added progress tracking output.
* Added handling of exceptions within tasks.

0.1.0 - 28/08/2012
------------------

* Initial release.
* Added management of dependancies between tasks.
* Added automatic generation of command line interface.
